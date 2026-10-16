import json
import time
import logging
from typing import Optional, Dict
from datetime import datetime, timedelta
import requests
try:
    import websocket
except ImportError:
    websocket = None
import threading
import pandas as pd

from config import (
    TWELVEDATA_API_KEY,
    PRICE_CACHE_TTL, HISTORY_CACHE_TTL,
    DEFAULT_TIMEFRAME, HISTORY_PERIOD,
    TWELVEDATA_WS_URL, FUTURES_ONLY_SYMBOLS
)
from utils import cache_key, normalize_symbol

logger = logging.getLogger(__name__)


class DataFetcher:
    _instance = None

    def __init__(self):
        self.price_cache = {}
        self.history_cache = {}
        self.subscribed_symbols = set([
            "BTCUSDT", "ETHUSDT", "XAUUSDT"
        ])
        self.ws = None
        self.ws_thread = None
        self.active_source = "binance"

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # =========================================================
    # WEBSOCKET
    # =========================================================

    def start_websocket(self):
        self._start_twelve_ws()

    def _start_twelve_ws(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
        self.ws = None
        self.ws_thread = None

        if not TWELVEDATA_API_KEY:
            logger.error("❌ Twelve Data: pas de clé API")
            return

        def on_open(ws):
            formatted = [self._format_symbol(s) for s in sorted(self.subscribed_symbols)]
            ws.send(json.dumps({"action": "subscribe", "params": {"symbols": ",".join(formatted)}}))
            self.active_source = "twelve"
            logger.info("✅ Twelve Data WebSocket actif")

        def on_error(ws, err):
            logger.error(f"Twelve WS error: {err}")

        def on_close(ws, *args):
            logger.warning("⚠️ Twelve Data WebSocket fermé")

        self.ws = websocket.WebSocketApp(
            f"{TWELVEDATA_WS_URL}?apikey={TWELVEDATA_API_KEY}",
            on_open=on_open,
            on_message=lambda ws, msg: self._on_twelve_message(msg),
            on_error=on_error,
            on_close=on_close
        )
        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()

    def _on_twelve_message(self, message):
        """Parse le prix et met à jour le cache. Les alertes sont gérées par AlertManager."""
        try:
            data = json.loads(message)
            if data.get("event") != "price":
                return
            symbol = normalize_symbol(data.get("symbol", ""))
            price = float(data.get("price", 0))
            raw_bid = data.get("bid")
            raw_ask = data.get("ask")
            if raw_bid is not None and raw_ask is not None:
                bid = float(raw_bid)
                ask = float(raw_ask)
            else:
                spread = max(price * 0.0005, 0.0001)
                bid = price - spread / 2
                ask = price + spread / 2

            old_price = self.price_cache.get(symbol, {}).get("price", price)

            self.price_cache[symbol] = {
                "price": price,
                "bid": bid,
                "ask": ask,
                "prev_price": old_price,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.debug(f"Twelve WS parse error: {e}")

    # =========================================================
    # PRIX TEMPS RÉEL
    # =========================================================

    def get_cached_price(self, symbol: str) -> Optional[Dict]:
        symbol = normalize_symbol(symbol)
        # Pas de cache pour les actifs Binance : prix toujours en temps réel
        if symbol.endswith("USDT"):
            return None
        if symbol in self.price_cache:
            if time.time() - self.price_cache[symbol]["timestamp"] < PRICE_CACHE_TTL:
                return self.price_cache[symbol]
        return None

    async def get_realtime_price(self, symbol: str, force_fresh: bool = False) -> Optional[Dict]:
        symbol = normalize_symbol(symbol)
        # Actifs Binance : toujours en temps réel, pas de cache
        if symbol.endswith("USDT"):
            return await self._fetch_price(symbol)
        if not force_fresh:
            cached = self.get_cached_price(symbol)
            if cached:
                return cached
        price = await self._fetch_price(symbol)
        if price:
            self.price_cache[symbol] = price
        return price

    async def _fetch_price(self, symbol: str) -> Optional[Dict]:
        # 1. Binance REST public multi-miroirs (data-api.binance.vision n'est jamais géo-bloqué)
        binance_sym = symbol

        if symbol.endswith("USDT"):
            if symbol in FUTURES_ONLY_SYMBOLS:
                # Pas de marché Spot (ex: XAUUSDT, perpétuel TradFi) : on lit uniquement USD-M Futures.
                price_urls = (f"https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol={binance_sym}",)
            else:
                price_urls = (
                    f"https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol={binance_sym}",
                    f"https://api.binance.com/api/v3/ticker/bookTicker?symbol={binance_sym}",
                    f"https://api1.binance.com/api/v3/ticker/bookTicker?symbol={binance_sym}",
                    f"https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol={binance_sym}",
                )
            for url in price_urls:
                try:
                    r = requests.get(url, timeout=5)
                    if r.status_code == 200:
                        data = r.json()
                        bid = float(data.get("bidPrice", 0) or 0)
                        ask = float(data.get("askPrice", 0) or 0)
                        if bid > 0 or ask > 0:
                            price = (bid + ask) / 2.0 if (bid and ask) else (bid or ask)
                            return {"price": price, "bid": bid or price, "ask": ask or price, "timestamp": time.time()}
                except Exception as e:
                    logger.debug(f"Binance mirror price error {binance_sym} ({url}): {e}")

            if symbol.endswith("USDT"):
                return None

        # 2. Source Twelve Data pour les autres symboles (si clé présente)
        if TWELVEDATA_API_KEY:
            try:
                td_symbol = self._format_symbol(symbol)
                url = f"https://api.twelvedata.com/quote?symbol={td_symbol}&apikey={TWELVEDATA_API_KEY}"
                r = requests.get(url, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    if "close" in data or "price" in data:
                        price = float(data.get("close") or data.get("price", 0))
                        if price > 0:
                            bid = float(data.get("bid", price - max(price * 0.0005, 0.0001)))
                            ask = float(data.get("ask", price + max(price * 0.0005, 0.0001)))
                            return {"price": price, "bid": bid, "ask": ask, "timestamp": time.time()}
            except Exception as e:
                logger.warning(f"Price error {symbol}: {e}")

        return None

    # =========================================================
    # DONNÉES HISTORIQUES
    # =========================================================

    async def get_historical_data(self, symbol: str, timeframe: str = DEFAULT_TIMEFRAME, period: str = HISTORY_PERIOD) -> Optional[pd.DataFrame]:
        symbol = normalize_symbol(symbol)
        # Actifs Binance : toujours frais à la demande
        if symbol.endswith("USDT"):
            return await self._fetch_history(symbol, timeframe)
        # Actifs TwelveData : cache conservé pour respecter les quotas API
        key = cache_key(symbol, timeframe, period)
        if key in self.history_cache and time.time() - self.history_cache[key]["timestamp"] < HISTORY_CACHE_TTL:
            return self.history_cache[key]["data"]
        df = await self._fetch_history(symbol, timeframe)
        if df is not None and not df.empty:
            self.history_cache[key] = {"data": df, "timestamp": time.time()}
            return df
        return None

    async def _fetch_history(self, symbol: str, timeframe: str):
        # 1. Binance REST public multi-miroirs (data-api.binance.vision fonctionne partout, même US/Render)
        if symbol.endswith("USDT"):
            target_sym = symbol
            try:
                from binance_manager import get_klines_dataframe
                hist_market = "futures" if target_sym in FUTURES_ONLY_SYMBOLS else "spot"
                df = get_klines_dataframe(target_sym, timeframe, market_type=hist_market, limit=500)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.warning(f"Binance History error {target_sym}: {e}")

            if symbol.endswith("USDT"):
                return None

        # 2. TwelveData — pour les actifs hors Binance (forex, matières premières) si clé configurée
        if TWELVEDATA_API_KEY:
            try:
                td_symbol = self._format_symbol(symbol)
                interval = {
                    "1m": "1min",
                    "5m": "5min",
                    "15m": "15min",
                    "1h": "1h",
                    "4h": "4h",
                    "1d": "1day",
                }.get(timeframe, "1day")
                url = f"https://api.twelvedata.com/time_series?symbol={td_symbol}&interval={interval}&outputsize=500&apikey={TWELVEDATA_API_KEY}"
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json().get("values", [])
                    if data:
                        df = pd.DataFrame(data).rename(columns={
                            "datetime": "Date", "open": "Open", "high": "High",
                            "low": "Low", "close": "Close", "volume": "Volume"
                        })
                        df = df.iloc[::-1]
                        df["Date"] = pd.to_datetime(df["Date"])
                        df.set_index("Date", inplace=True)
                        for col in ("Open", "High", "Low", "Close", "Volume"):
                            if col not in df.columns:
                                df[col] = 0.0
                        return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
            except Exception as e:
                logger.warning(f"History error {symbol}: {e}")

        return None

    # =========================================================
    # FORMATAGE SYMBOLES
    # =========================================================

    def _format_symbol(self, symbol: str) -> str:
        s = symbol.upper()
        if len(s) == 6:
            return f"{s[:3]}/{s[3:]}"
        return s
