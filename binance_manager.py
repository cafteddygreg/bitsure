"""
binance_manager.py
-------------------
Encapsule toute la communication avec l'API Binance (spot + futures).
Ne jamais logguer api_key / api_secret en clair (voir trading_logger.py).

Dépendance : pip install python-binance
"""

import logging
import hashlib
import hmac
import math
import time
import urllib.parse
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Literal

import pandas as pd
import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from trading_config import get_binance_credentials, mark_credentials_invalid, get_config
from trading_safety import SafetyError, assert_trading_allowed
from utils import normalize_symbol

logger = logging.getLogger("binance_manager")

MarketType = Literal["spot", "futures"]


class _NoPingClient(Client):
    """Client python-binance qui n'appelle JAMAIS self.ping() sur api.binance.com dans __init__.
    Évite le blocage géographique HTTP 451 (Service unavailable from a restricted location)
    lorsque le serveur Render est hébergé aux États-Unis."""

    def ping(self):
        return {}


def _build_resilient_client(api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: bool = False) -> Client:
    """Construit un Client Binance sans ping initial bloquant et oriente les URLs vers des endpoints accessibles."""
    try:
        client = _NoPingClient(api_key, api_secret, testnet=testnet)
    except Exception:
        # Fallback ultime si une version de python-binance appelle autre chose dans __init__
        client = object.__new__(_NoPingClient)
        client.API_KEY = api_key or ""
        client.API_SECRET = api_secret or ""
        client.session = requests.Session()
        if api_key:
            client.session.headers.update({"X-MBX-APIKEY": api_key})
        client.testnet = testnet
        client.tld = "com"
        client._requests_params = None
        client.response = None
        client.timestamp_offset = 0

    if testnet:
        client.API_URL = "https://testnet.binance.vision/api"
        client.FUTURES_URL = "https://testnet.binancefuture.com/fapi"
        client.FUTURES_DATA_URL = "https://testnet.binancefuture.com/futures/data"
    else:
        # Sur Live, data-api.binance.vision ou api4.binance.com passent mieux les filtres
        client.API_URL = "https://api4.binance.com/api"
        client.FUTURES_URL = "https://fapi.binance.com/fapi"
    return client


def _signed_rest_get(
    api_key: str,
    api_secret: str,
    path: str,
    params: Optional[dict] = None,
    *,
    market_type: MarketType = "futures",
    testnet: bool = True,
) -> Optional[dict | list]:
    """Effectue une requête GET signée HMAC-SHA256 directe vers Binance (Spot ou Futures, Testnet ou Live).
    Ne mélange jamais les endpoints Testnet et Live ni Spot et Futures."""
    if market_type == "futures":
        bases = (
            ("https://testnet.binancefuture.com",)
            if testnet
            else ("https://fapi.binance.com",)
        )
    else:
        bases = (
            ("https://testnet.binance.vision",)
            if testnet
            else ("https://api4.binance.com", "https://api1.binance.com", "https://api.binance.com")
        )

    last_err = None
    for base in bases:
        try:
            q = dict(params or {})
            q["timestamp"] = int(time.time() * 1000)
            q.setdefault("recvWindow", 10000)
            query_str = urllib.parse.urlencode(q)
            sig = hmac.new(api_secret.encode("utf-8"), query_str.encode("utf-8"), hashlib.sha256).hexdigest()
            url = f"{base}{path}?{query_str}&signature={sig}"
            r = requests.get(url, headers={"X-MBX-APIKEY": api_key}, timeout=7)
            if r.status_code == 200:
                return r.json()
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:
            last_err = str(exc)
            continue
    if last_err:
        logger.warning("Direct signed REST GET %s failed (%s/%s): %s", path, market_type, "testnet" if testnet else "live", last_err)
    return None


def _signed_rest_request(
    method: str,
    api_key: str,
    api_secret: str,
    path: str,
    params: Optional[dict] = None,
    *,
    market_type: MarketType = "futures",
    testnet: bool = True,
) -> dict | list:
    """Exécute une requête signée POST/DELETE directe vers Binance (Testnet ou Live) sans mélange d'environnements."""
    if market_type == "futures":
        bases = (
            ("https://testnet.binancefuture.com",)
            if testnet
            else ("https://fapi.binance.com",)
        )
    else:
        bases = (
            ("https://testnet.binance.vision",)
            if testnet
            else ("https://api4.binance.com", "https://api1.binance.com", "https://api.binance.com")
        )

    last_err = "Erreur réseau Binance"
    for base in bases:
        try:
            q = {k: v for k, v in (params or {}).items() if v is not None}
            q["timestamp"] = int(time.time() * 1000)
            q.setdefault("recvWindow", 10000)
            query_str = urllib.parse.urlencode(q)
            sig = hmac.new(api_secret.encode("utf-8"), query_str.encode("utf-8"), hashlib.sha256).hexdigest()
            url = f"{base}{path}?{query_str}&signature={sig}"
            r = requests.request(method.upper(), url, headers={"X-MBX-APIKEY": api_key}, timeout=8)
            if r.status_code == 200:
                return r.json()
            try:
                err_json = r.json()
                last_err = f"Code {err_json.get('code')}: {err_json.get('msg')}"
            except Exception:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            # Si c'est une erreur métier Binance (ex: -2019 marge insuffisante), inutile d'essayer un autre miroir
            if r.status_code == 400 and "Code -" in last_err:
                break
        except Exception as exc:
            last_err = str(exc)
            continue
    raise BinanceClientError(last_err)


class BinanceClientError(Exception):
    """Erreur applicative levée par ce module (message safe à afficher à l'utilisateur)."""


ORDER_CONTEXT_AUTOTRADE = "autotrade"
ORDER_CONTEXT_MANUAL_AUTHENTICATED = "manual_authenticated"
ORDER_CONTEXT_EMERGENCY = "emergency_stop"
_ALLOWED_ORDER_CONTEXTS = {
    ORDER_CONTEXT_AUTOTRADE,
    ORDER_CONTEXT_MANUAL_AUTHENTICATED,
    ORDER_CONTEXT_EMERGENCY,
}


def _assert_order_context_allowed(user_id: int, execution_context: Optional[str], *, require_auto_trade: bool) -> None:
    """Fail closed before any real Binance order can be sent.

    Telegram/webhooks/scanners must not rely on their route-level checks only: every
    backend order primitive must receive an explicit, already-authorized execution
    context. AutoTrade contexts do not require a fresh PIN per order, but they are
    accepted only while AutoTrade remains enabled and safety state is valid.
    """
    if execution_context not in _ALLOWED_ORDER_CONTEXTS:
        raise BinanceClientError("Ordre réel refusé: contexte d'exécution non autorisé.")

    config = get_config(user_id)
    try:
        assert_trading_allowed(
            config,
            require_auto_trade=(require_auto_trade or execution_context == ORDER_CONTEXT_AUTOTRADE),
        )
    except SafetyError as e:
        raise BinanceClientError(f"Ordre réel refusé: {e}")

    if execution_context == ORDER_CONTEXT_AUTOTRADE and not config.auto_trade:
        raise BinanceClientError("Ordre automatique refusé: AutoTrade est désactivé.")


def _client_for_user(user_id: int, market_type: Optional[MarketType] = None) -> Client:
    creds = get_binance_credentials(user_id, market_type=market_type)
    if not creds or not creds["api_key"] or not creds["api_secret"]:
        raise BinanceClientError(
            "Aucune clé API Binance configurée. Utilise /setapikeys pour les ajouter."
        )
    if not creds["is_valid"]:
        raise BinanceClientError(
            "Tes clés API Binance semblent invalides. Merci de les reconfigurer."
        )

    return _build_resilient_client(creds["api_key"], creds["api_secret"], testnet=bool(creds["testnet"]))


def _public_client() -> Client:
    return _build_resilient_client()


_SPOT_PUBLIC_BASES = (
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api.binance.com",
)

_FUTURES_PUBLIC_BASES = (
    "https://fapi.binance.com",
)


def _extract_order_fill_price(order: Optional[dict]) -> Optional[float]:
    """Extrait le prix réel d'exécution (fill) depuis la réponse d'ordre Binance."""
    if not isinstance(order, dict):
        return None
    try:
        avg_price = float(order.get("avgPrice") or 0.0)
        if avg_price > 0:
            return avg_price
    except (TypeError, ValueError):
        pass

    fills = order.get("fills")
    if isinstance(fills, list) and fills:
        total_qty = 0.0
        total_cost = 0.0
        for f in fills:
            try:
                p = float(f.get("price") or 0.0)
                q = float(f.get("qty") or 0.0)
                if p > 0 and q > 0:
                    total_qty += q
                    total_cost += p * q
            except (TypeError, ValueError):
                continue
        if total_qty > 0:
            return total_cost / total_qty

    try:
        exec_qty = float(order.get("executedQty") or 0.0)
        cum_quote = float(order.get("cummulativeQuoteQty") or order.get("cumQuote") or 0.0)
        if exec_qty > 0 and cum_quote > 0:
            return cum_quote / exec_qty
    except (TypeError, ValueError):
        pass

    try:
        price = float(order.get("price") or 0.0)
        if price > 0:
            return price
    except (TypeError, ValueError):
        pass

    return None


def get_tradable_symbols(market_type: MarketType = "futures", quote_asset: str = "USDT") -> list[str]:
    """Return active Binance symbols for the requested market and quote asset without mixing Spot and Futures."""
    if market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché invalide : {market_type}")

    bases = _FUTURES_PUBLIC_BASES if market_type == "futures" else _SPOT_PUBLIC_BASES
    path = "/fapi/v1/exchangeInfo" if market_type == "futures" else "/api/v3/exchangeInfo"

    for base in bases:
        try:
            r = requests.get(f"{base}{path}", timeout=6)
            if r.status_code == 200:
                info = r.json()
                symbols = [
                    item["symbol"]
                    for item in info.get("symbols", [])
                    if item.get("quoteAsset") == quote_asset and item.get("status") == "TRADING"
                ]
                if symbols:
                    return sorted(set(symbols))
        except Exception:
            continue

    try:
        client = _public_client()
        info = client.futures_exchange_info() if market_type == "futures" else client.get_exchange_info()
        symbols = [
            item["symbol"]
            for item in info.get("symbols", [])
            if item.get("quoteAsset") == quote_asset and item.get("status") == "TRADING"
        ]
        return sorted(set(symbols))
    except Exception as e:
        raise BinanceClientError(f"Erreur Binance (liste symboles) : {e}")


def get_klines_dataframe(
    symbol: str,
    timeframe: str,
    market_type: MarketType = "futures",
    limit: int = 500,
) -> Optional[pd.DataFrame]:
    """Fetch public Binance OHLCV data as a DataFrame compatible with SignalEngine.
    Prioritizes the exact market endpoint (Futures vs Spot).
    """
    symbol = normalize_symbol(symbol)
    klines = None

    if market_type == "futures":
        endpoints = [
            *(f"{b}/fapi/v1/klines" for b in _FUTURES_PUBLIC_BASES),
            "https://data-api.binance.vision/api/v3/klines",
        ]
    else:
        endpoints = [
            *(f"{b}/api/v3/klines" for b in _SPOT_PUBLIC_BASES),
        ]

    for url in endpoints:
        try:
            r = requests.get(
                url,
                params={"symbol": symbol, "interval": timeframe, "limit": min(limit, 1000)},
                timeout=7,
            )
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    klines = data
                    break
        except Exception:
            continue

    if not klines:
        try:
            client = _public_client()
            if market_type == "futures":
                klines = client.futures_klines(symbol=symbol, interval=timeframe, limit=limit)
            else:
                klines = client.get_klines(symbol=symbol, interval=timeframe, limit=limit)
        except Exception as e:
            logger.warning(f"Binance klines fallback failed for {symbol}: {e}")
            return None

    if not klines:
        return None

    df = pd.DataFrame(
        klines,
        columns=[
            "OpenTime", "Open", "High", "Low", "Close", "Volume",
            "CloseTime", "QuoteAssetVolume", "NumberOfTrades",
            "TakerBuyBaseVolume", "TakerBuyQuoteVolume", "Ignore",
        ],
    )
    df["Date"] = pd.to_datetime(df["OpenTime"], unit="ms")
    df.set_index("Date", inplace=True)
    return df[["Open", "High", "Low", "Close", "Volume"]].astype(float)



def make_client_order_id(prefix: str, unique_key: str, max_len: int = 36) -> str:
    """Build a deterministic Binance-compatible client order id."""
    safe_prefix = "".join(ch for ch in prefix if ch.isalnum() or ch in "_-")[:8] or "ord"
    digest = hashlib.sha256(str(unique_key).encode("utf-8")).hexdigest()[:24]
    return f"{safe_prefix}_{digest}"[:max_len]


def get_price(user_id: int, symbol: str, market_type: MarketType = "futures") -> float:
    symbol = normalize_symbol(symbol)
    if market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché invalide : {market_type}")
    try:
        client = _client_for_user(user_id, market_type=market_type)
        if market_type == "futures":
            ticker = client.futures_symbol_ticker(symbol=symbol)
        else:
            ticker = client.get_symbol_ticker(symbol=symbol)
        return float(ticker["price"])
    except Exception as first_err:
        is_testnet = False
        try:
            creds = get_binance_credentials(user_id, market_type=market_type)
            if creds is not None:
                is_testnet = bool(creds.get("testnet", False))
            else:
                is_testnet = bool(get_config(user_id).testnet)
        except Exception:
            is_testnet = False

        if market_type == "futures":
            urls = (
                (f"https://testnet.binancefuture.com/fapi/v1/ticker/price?symbol={symbol}",)
                if is_testnet
                else (f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",)
            )
        else:
            urls = (
                (f"https://testnet.binance.vision/api/v3/ticker/price?symbol={symbol}",)
                if is_testnet
                else (
                    f"https://data-api.binance.vision/api/v3/ticker/price?symbol={symbol}",
                    f"https://api1.binance.com/api/v3/ticker/price?symbol={symbol}",
                )
            )
        for url in urls:
            try:
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    if "price" in data:
                        return float(data["price"])
            except Exception:
                continue
        msg = getattr(first_err, "message", str(first_err))
        raise BinanceClientError(f"Erreur Binance (prix {symbol}) : {msg}")


def get_account_balance(user_id: int, asset: str = "USDT", market_type: MarketType = "futures") -> float:
    try:
        client = _client_for_user(user_id, market_type=market_type)
        if market_type == "futures":
            balances = client.futures_account_balance()
            for b in balances:
                if b["asset"] == asset:
                    return float(b["balance"])
            return 0.0
        else:
            info = client.get_asset_balance(asset=asset)
            return float(info["free"]) if info else 0.0
    except BinanceAPIException as e:
        if e.code in (-2015, -2014):
            mark_credentials_invalid(user_id, str(e))
        raise BinanceClientError(f"Erreur Binance (solde) : {e.message}")
    except Exception:
        info = get_full_account_info(user_id, market_type=market_type)
        return float(info.get("available_balance", 0.0))


def get_symbol_filters(client: Client, symbol: str, market_type: MarketType) -> dict:
    """Récupère les filtres Binance (PRICE_FILTER, LOT_SIZE, etc.) du symbole via miroirs publics résilients."""
    symbol = normalize_symbol(symbol)
    bases = _FUTURES_PUBLIC_BASES if market_type == "futures" else _SPOT_PUBLIC_BASES
    path = "/fapi/v1/exchangeInfo" if market_type == "futures" else "/api/v3/exchangeInfo"

    for base in bases:
        try:
            params = {"symbol": symbol} if market_type == "spot" else None
            r = requests.get(f"{base}{path}", params=params, timeout=5)
            if r.status_code == 200:
                info = r.json()
                for s in info.get("symbols", []):
                    if s.get("symbol") == symbol:
                        return {f["filterType"]: f for f in s.get("filters", [])}
        except Exception:
            continue

    try:
        info = client.futures_exchange_info() if market_type == "futures" else client.get_exchange_info()
        for s in info.get("symbols", []):
            if s["symbol"] == symbol:
                return {f["filterType"]: f for f in s["filters"]}
    except Exception:
        pass

    # Fallback sécurisé standard si l'API exchangeInfo est momentanément injoignable
    if symbol.startswith("BTC"):
        return {
            "LOT_SIZE": {"stepSize": "0.001", "minQty": "0.001"},
            "PRICE_FILTER": {"tickSize": "0.10"},
            "MIN_NOTIONAL": {"notional": "5.0"},
        }
    return {
        "LOT_SIZE": {"stepSize": "0.01", "minQty": "0.01"},
        "PRICE_FILTER": {"tickSize": "0.01"},
        "MIN_NOTIONAL": {"notional": "5.0"},
    }


def _quantize_down(value: float, quantum: str) -> Decimal:
    q = Decimal(str(quantum))
    if q <= 0:
        return Decimal(str(value))
    return (Decimal(str(value)) / q).to_integral_value(rounding=ROUND_DOWN) * q


def format_step_value(value: float, quantum: str) -> str:
    rounded = _quantize_down(value, quantum)
    return format(rounded.normalize(), "f")


def round_step_size(quantity: float, step_size: str) -> float:
    return float(_quantize_down(quantity, step_size))


def format_price_for_symbol(price: float, filters: dict) -> str:
    tick_size = filters.get("PRICE_FILTER", {}).get("tickSize", "0.00000001")
    return format_step_value(price, tick_size)


def set_leverage(user_id: int, symbol: str, leverage: int) -> None:
    symbol = normalize_symbol(symbol)
    client = _client_for_user(user_id, market_type="futures")
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
    except BinanceAPIException as e:
        raise BinanceClientError(f"Impossible de définir le levier x{leverage} : {e.message}")


def open_position(
    user_id: int,
    symbol: str,
    direction: str,          # "BUY" ou "SELL"
    quantity: float,
    sl_price: Optional[float],
    tp_price: Optional[float],
    market_type: MarketType = "futures",
    leverage: int = 1,
    client_order_id: Optional[str] = None,
    execution_context: Optional[str] = None,
) -> dict:
    """
    Ouvre une position au marché, puis place SL/TP.
    Retourne un dict avec les IDs d'ordres et le prix réel d'exécution (à stocker dans la table `trades`).
    Lève BinanceClientError en cas d'échec (message safe pour l'utilisateur).
    """
    if market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché non supporté : {market_type}")

    _assert_order_context_allowed(
        user_id, execution_context, require_auto_trade=(execution_context == ORDER_CONTEXT_AUTOTRADE)
    )
    client = _client_for_user(user_id, market_type=market_type)
    symbol = normalize_symbol(symbol)
    direction = direction.upper()

    # Règles strictes Spot vs Futures
    if market_type == "spot":
        leverage = 1
        if direction == "SELL":
            raise BinanceClientError("Vente à découvert (SHORT) non supportée en mode Spot standard.")

    opened_order = None

    try:
        if market_type == "futures":
            remote_positions = get_open_binance_positions(user_id, market_type=market_type)
            same = [p for p in remote_positions if p["symbol"] == symbol and p["direction"] == direction]
            opposite_positions = [p for p in remote_positions if p["symbol"] == symbol and p["direction"] != direction]
            if same or opposite_positions:
                raise BinanceClientError(
                    f"Ouverture refusée: position Binance existante sur {symbol} "
                    f"({remote_positions})."
                )

        filters = get_symbol_filters(client, symbol, market_type)
        step_size = filters.get("LOT_SIZE", {}).get("stepSize") or filters.get(
            "MARKET_LOT_SIZE", {}
        ).get("stepSize", "0.001")
        min_qty = float(filters.get("LOT_SIZE", {}).get("minQty") or filters.get("MARKET_LOT_SIZE", {}).get("minQty", "0.0"))
        min_notional = float(filters.get("MIN_NOTIONAL", {}).get("notional") or filters.get("NOTIONAL", {}).get("minNotional", "0.0"))

        quantity = round_step_size(quantity, step_size)
        if quantity <= 0 or (min_qty > 0 and quantity < min_qty):
            raise BinanceClientError(f"Quantité calculée ({quantity}) trop faible par rapport aux règles Binance (minQty: {min_qty}).")

        price_for_notional = get_price(user_id, symbol, market_type)
        notional = quantity * price_for_notional
        if min_notional > 0 and notional < min_notional:
            raise BinanceClientError(f"Valeur notionnelle ({notional:.2f} USDT) inférieure au minimum requis par Binance ({min_notional:.2f} USDT).")

        result: dict = {"quantity": quantity, "executed_price": None}

        if market_type == "futures":
            if leverage:
                set_leverage(user_id, symbol, int(leverage))

            order_params = {
                "symbol": symbol, "side": direction, "type": "MARKET", "quantity": quantity,
            }
            if client_order_id:
                order_params["newClientOrderId"] = client_order_id
            order = client.futures_create_order(**order_params)
            opened_order = order
            result["order_id"] = order["orderId"]
            result["client_order_id"] = order.get("clientOrderId")
            result["executed_price"] = _extract_order_fill_price(order)

            opposite = "SELL" if direction == "BUY" else "BUY"

            if sl_price or tp_price:
                target_types = set()
                if sl_price:
                    target_types.add("STOP_MARKET")
                if tp_price:
                    target_types.add("TAKE_PROFIT_MARKET")
                _cancel_conflicting_futures_protective_orders(
                    client,
                    symbol,
                    side=opposite,
                    order_types=target_types,
                )

            if sl_price:
                sl_order = client.futures_create_order(
                    symbol=symbol, side=opposite, type="STOP_MARKET",
                    stopPrice=format_price_for_symbol(sl_price, filters), closePosition=True,
                )
                result["sl_order_id"] = sl_order["orderId"]

            if tp_price:
                tp_order = client.futures_create_order(
                    symbol=symbol, side=opposite, type="TAKE_PROFIT_MARKET",
                    stopPrice=format_price_for_symbol(tp_price, filters), closePosition=True,
                )
                result["tp_order_id"] = tp_order["orderId"]

        else:  # spot
            order_params = {"symbol": symbol, "side": direction, "type": "MARKET", "quantity": quantity}
            if client_order_id:
                order_params["newClientOrderId"] = client_order_id
            order = client.create_order(**order_params)
            result["order_id"] = order["orderId"]
            result["client_order_id"] = order.get("clientOrderId")
            result["executed_price"] = _extract_order_fill_price(order)
            result["sl_order_id"] = None
            result["tp_order_id"] = None

        return result

    except (BinanceAPIException, BinanceOrderException) as e:
        if getattr(e, "code", None) in (-2015, -2014):
            mark_credentials_invalid(user_id, str(e))
        if market_type == "futures" and opened_order:
            opposite = "SELL" if direction == "BUY" else "BUY"
            try:
                client.futures_create_order(
                    symbol=symbol, side=opposite, type="MARKET",
                    quantity=quantity, reduceOnly=True,
                )
            except Exception as close_error:
                logger.critical(
                    "Position %s potentiellement ouverte sans protection pour user=%s après échec SL/TP: %s",
                    symbol, user_id, close_error,
                )
                raise BinanceClientError(
                    "Ordre principal ouvert mais protection SL/TP échouée; "
                    "fermeture automatique impossible. Vérifie Binance immédiatement."
                )
            raise BinanceClientError(
                "Ordre principal ouvert puis refermé car la protection SL/TP a échoué."
            )
        raise BinanceClientError(f"Erreur Binance à l'ouverture : {getattr(e, 'message', str(e))}")



def get_available_balance(user_id: int, market_type: MarketType = "futures", asset: str = "USDT") -> float:
    if market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché non supporté : {market_type}")
    client = _client_for_user(user_id, market_type=market_type)
    try:
        if market_type == "futures":
            acc = client.futures_account()
            return float(acc.get("availableBalance", 0.0))
        info = client.get_asset_balance(asset=asset)
        return float(info["free"]) if info else 0.0
    except BinanceAPIException as e:
        raise BinanceClientError(f"Erreur Binance (marge disponible) : {e.message}")


def get_open_binance_positions(user_id: int, market_type: MarketType = "futures") -> list[dict]:
    """Return real open positions from Binance for reconciliation/risk checks."""
    if market_type != "futures":
        return []
    client = _client_for_user(user_id, market_type="futures")
    try:
        positions = []
        for pos in client.futures_position_information():
            amt = float(pos.get("positionAmt", 0.0))
            if amt == 0:
                continue
            positions.append({
                "symbol": pos["symbol"],
                "direction": "BUY" if amt > 0 else "SELL",
                "quantity": abs(amt),
                "entry_price": float(pos.get("entryPrice", 0.0)),
                "mark_price": float(pos.get("markPrice", 0.0)),
            })
        return positions
    except BinanceAPIException as e:
        raise BinanceClientError(f"Erreur Binance (positions ouvertes) : {e.message}")


def get_open_binance_orders(user_id: int, market_type: MarketType = "futures", symbol: Optional[str] = None) -> list[dict]:
    """Return open Binance orders for reconciliation."""
    if market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché non supporté : {market_type}")
    client = _client_for_user(user_id, market_type=market_type)
    try:
        if market_type == "futures":
            return client.futures_get_open_orders(symbol=symbol) if symbol else client.futures_get_open_orders()
        return client.get_open_orders(symbol=symbol) if symbol else client.get_open_orders()
    except BinanceAPIException as e:
        raise BinanceClientError(f"Erreur Binance (ordres ouverts) : {e.message}")


def close_position(
    user_id: int,
    symbol: str,
    direction: str,
    quantity: float,
    market_type: MarketType = "futures",
    execution_context: Optional[str] = None,
) -> dict:
    """Ferme une position au marché (côté opposé à l'ouverture)."""
    if market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché non supporté : {market_type}")

    _assert_order_context_allowed(user_id, execution_context, require_auto_trade=(execution_context == ORDER_CONTEXT_AUTOTRADE))
    client = _client_for_user(user_id, market_type=market_type)
    symbol = symbol.upper()
    direction = direction.upper()
    if market_type == "spot" and direction == "SELL":
        raise BinanceClientError("Fermeture d'une position SHORT impossible en mode Spot standard.")
    opposite = "SELL" if direction == "BUY" else "BUY"

    try:
        if market_type == "futures":
            remote_positions = get_open_binance_positions(user_id, market_type=market_type)
            matching = [
                p for p in remote_positions
                if p["symbol"] == symbol
                and p["direction"] == direction
                and abs(float(p["quantity"]) - float(quantity)) <= max(float(quantity) * 0.001, 1e-12)
            ]
            if not matching:
                raise BinanceClientError(
                    f"Fermeture refusée: aucune position Binance {symbol} {direction} "
                    f"avec quantité attendue {quantity}."
                )
        filters = get_symbol_filters(client, symbol, market_type)
        step_size = filters.get("LOT_SIZE", {}).get("stepSize") or filters.get("MARKET_LOT_SIZE", {}).get("stepSize", "0.001")
        qty = format_step_value(quantity, step_size)
        if market_type == "futures":
            order = client.futures_create_order(
                symbol=symbol, side=opposite, type="MARKET",
                quantity=qty, reduceOnly=True,
            )
        else:
            order = client.create_order(
                symbol=symbol, side=opposite, type="MARKET", quantity=qty
            )
        return {
            "order_id": order["orderId"],
            "executed_price": _extract_order_fill_price(order),
        }
    except (BinanceAPIException, BinanceOrderException) as e:
        raise BinanceClientError(f"Erreur Binance à la fermeture : {getattr(e, 'message', str(e))}")


def cancel_order(user_id: int, symbol: str, order_id: str, market_type: MarketType = "futures", execution_context: Optional[str] = None) -> None:
    _assert_order_context_allowed(user_id, execution_context, require_auto_trade=(execution_context == ORDER_CONTEXT_AUTOTRADE))
    client = _client_for_user(user_id, market_type=market_type)
    try:
        if market_type == "futures":
            client.futures_cancel_order(symbol=symbol, orderId=order_id)
        else:
            client.cancel_order(symbol=symbol, orderId=order_id)
    except BinanceAPIException as e:
        # Non bloquant : l'ordre est peut-être déjà exécuté/annulé.
        logger.warning("Annulation ordre %s (%s) impossible : %s", order_id, symbol, e.message)


def _find_futures_protective_orders(
    client: Client,
    symbol: str,
    side: Optional[str] = None,
    order_types: Optional[set[str]] = None,
) -> list[dict]:
    """Détecte les ordres protecteurs closePosition/reduceOnly déjà ouverts sur Binance Futures."""
    symbol = normalize_symbol(symbol)
    target_types = {t.upper() for t in (order_types or {"STOP_MARKET", "STOP", "TAKE_PROFIT_MARKET", "TAKE_PROFIT"})}
    if not hasattr(client, "futures_get_open_orders"):
        return []
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol) or []
    except Exception as e:
        logger.warning("Impossible de lister les ordres protecteurs ouverts sur %s : %s", symbol, e)
        return []

    matched: list[dict] = []
    for o in open_orders:
        if not isinstance(o, dict):
            continue
        o_sym = normalize_symbol(str(o.get("symbol") or symbol))
        if o_sym != symbol:
            continue
        o_type = str(o.get("type") or o.get("origType") or "").upper()
        if o_type not in target_types:
            continue
        if side and str(o.get("side") or "").upper() != side.upper():
            continue
        is_close_pos = str(o.get("closePosition", "")).lower() in ("true", "1") or bool(o.get("closePosition"))
        is_reduce_only = str(o.get("reduceOnly", "")).lower() in ("true", "1") or bool(o.get("reduceOnly"))
        if is_close_pos or is_reduce_only or o_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET"):
            matched.append(o)
    return matched


def _cancel_conflicting_futures_protective_orders(
    client: Client,
    symbol: str,
    side: Optional[str] = None,
    order_types: Optional[set[str]] = None,
    exclude_order_ids: Optional[set[str]] = None,
) -> list[str]:
    """Annule tous les ordres protecteurs closePosition en conflit avant d'en créer/remplacer un."""
    symbol = normalize_symbol(symbol)
    excluded = {str(oid) for oid in (exclude_order_ids or set()) if oid is not None}
    cancelled_ids: list[str] = []
    for o in _find_futures_protective_orders(client, symbol, side=side, order_types=order_types):
        oid = o.get("orderId")
        if oid is None or str(oid) in excluded:
            continue
        try:
            client.futures_cancel_order(symbol=symbol, orderId=oid)
            cancelled_ids.append(str(oid))
        except Exception as e:
            logger.warning("Annulation ordre protecteur en conflit %s (%s) impossible : %s", oid, symbol, e)
    return cancelled_ids


def _confirm_futures_protective_order(
    client: Client,
    symbol: str,
    created_order: Optional[dict],
    expected_side: str,
    expected_type: str,
) -> str:
    """Confirme que le nouvel ordre protecteur existe réellement avant de valider l'opération."""
    if not isinstance(created_order, dict) or created_order.get("orderId") is None:
        raise BinanceClientError(
            f"Confirmation SL/TP échouée sur {symbol}: aucun orderId retourné par Binance."
        )
    new_oid = str(created_order["orderId"])
    status = str(created_order.get("status") or "NEW").upper()
    if status in ("CANCELED", "EXPIRED", "REJECTED"):
        raise BinanceClientError(
            f"Confirmation SL/TP échouée sur {symbol}: ordre #{new_oid} en statut {status}."
        )
    if hasattr(client, "futures_get_open_orders"):
        try:
            open_orders = client.futures_get_open_orders(symbol=symbol)
            if isinstance(open_orders, list) and open_orders:
                open_ids = {str(o.get("orderId")) for o in open_orders if isinstance(o, dict) and o.get("orderId") is not None}
                if new_oid not in open_ids:
                    raise BinanceClientError(
                        f"Confirmation SL/TP échouée sur {symbol}: le nouvel ordre #{new_oid} est absent des ordres ouverts Binance."
                    )
        except BinanceClientError:
            raise
        except Exception as e:
            logger.debug("Vérification open_orders post-création non concluante sur %s: %s", symbol, e)
    return new_oid


def replace_futures_stop_loss_order(
    user_id: int,
    symbol: str,
    direction: str,
    new_sl_price: float,
    old_sl_order_id: Optional[str] = None,
    execution_context: Optional[str] = None,
) -> str:
    """Remplace l'ordre STOP_MARKET sur Binance Futures lors d'un déplacement de Trailing Stop.

    Garanties de sécurité :
    - Détecte tous les ordres STOP_MARKET closePosition existants dans la même direction.
    - Si un ordre STOP_MARKET existant a déjà exactement le même stopPrice formaté, le conserve.
    - Crée le nouvel ordre AVANT d'annuler l'ancien lorsque Binance l'accepte, ou annule les ordres
      STOP_MARKET en conflit (erreur -4130 closePosition GTE existant) et recrée immédiatement
      la protection dans le même flux atomique.
    - Confirme que le nouveau SL existe réellement avant de retourner son orderId.
    """
    _assert_order_context_allowed(
        user_id,
        execution_context,
        require_auto_trade=(execution_context == ORDER_CONTEXT_AUTOTRADE),
    )
    client = _client_for_user(user_id, market_type="futures")
    symbol = normalize_symbol(symbol)
    opposite = "SELL" if direction.upper() == "BUY" else "BUY"
    filters = get_symbol_filters(client, symbol, "futures")
    formatted_stop = format_price_for_symbol(new_sl_price, filters)

    existing_sl_orders = _find_futures_protective_orders(
        client,
        symbol,
        side=opposite,
        order_types={"STOP_MARKET", "STOP"},
    )

    # Si un ordre STOP_MARKET actif possède déjà ce stopPrice exact, éviter un doublon inutile
    for existing in existing_sl_orders:
        ex_id = existing.get("orderId")
        ex_stop = existing.get("stopPrice")
        try:
            if ex_id is not None and ex_stop is not None and abs(float(ex_stop) - float(formatted_stop)) <= 1e-9:
                # Nettoyer d'éventuels doublons supplémentaires tout en gardant celui-ci
                _cancel_conflicting_futures_protective_orders(
                    client,
                    symbol,
                    side=opposite,
                    order_types={"STOP_MARKET", "STOP"},
                    exclude_order_ids={str(ex_id)},
                )
                return str(ex_id)
        except (TypeError, ValueError):
            pass

    # Annuler d'abord l'ancien SL connu et tout autre STOP_MARKET closePosition en conflit
    # (Binance refuse un 2e STOP_MARKET closePosition=True dans la même direction avec -4130)
    ids_to_cancel: set[str] = set()
    if old_sl_order_id:
        ids_to_cancel.add(str(old_sl_order_id))
    for existing in existing_sl_orders:
        if existing.get("orderId") is not None:
            ids_to_cancel.add(str(existing["orderId"]))

    old_stop_price_fallback: Optional[str] = None
    for existing in existing_sl_orders:
        if existing.get("stopPrice") is not None:
            old_stop_price_fallback = str(existing["stopPrice"])
            break

    for oid in ids_to_cancel:
        cancel_order(user_id, symbol, oid, "futures", execution_context=execution_context)

    try:
        sl_order = client.futures_create_order(
            symbol=symbol,
            side=opposite,
            type="STOP_MARKET",
            stopPrice=formatted_stop,
            closePosition=True,
        )
    except BinanceAPIException as e:
        msg = getattr(e, "message", str(e))
        # Si un ordre STOP_MARKET closePosition a survécu ou est apparu entre-temps, purger et réessayer une fois
        if "closePosition" in msg or getattr(e, "code", None) == -4130:
            _cancel_conflicting_futures_protective_orders(
                client,
                symbol,
                side=opposite,
                order_types={"STOP_MARKET", "STOP"},
            )
            try:
                sl_order = client.futures_create_order(
                    symbol=symbol,
                    side=opposite,
                    type="STOP_MARKET",
                    stopPrice=formatted_stop,
                    closePosition=True,
                )
            except Exception as retry_err:
                # Ne jamais laisser volontairement la position sans protection : tenter de restaurer l'ancien SL
                if old_stop_price_fallback:
                    try:
                        client.futures_create_order(
                            symbol=symbol,
                            side=opposite,
                            type="STOP_MARKET",
                            stopPrice=old_stop_price_fallback,
                            closePosition=True,
                        )
                    except Exception:
                        pass
                raise BinanceClientError(f"Erreur Binance (mise à jour SL {symbol}) : {getattr(retry_err, 'message', str(retry_err))}")
        else:
            # Tenter de restaurer l'ancien SL si nous venons de l'annuler et que le nouveau prix est rejeté
            if ids_to_cancel and old_stop_price_fallback:
                try:
                    client.futures_create_order(
                        symbol=symbol,
                        side=opposite,
                        type="STOP_MARKET",
                        stopPrice=old_stop_price_fallback,
                        closePosition=True,
                    )
                except Exception:
                    pass
            raise BinanceClientError(f"Erreur Binance (mise à jour SL {symbol}) : {msg}")

    return _confirm_futures_protective_order(
        client,
        symbol,
        sl_order,
        expected_side=opposite,
        expected_type="STOP_MARKET",
    )


def test_connection(user_id: int) -> bool:
    """Utilisé par /setapikeys pour valider les clés dès leur saisie sur le marché configuré sans bascule silencieuse."""
    config = get_config(user_id)
    creds = get_binance_credentials(user_id, market_type=config.market_type)
    if not creds or not creds.get("api_key") or not creds.get("api_secret"):
        raise BinanceClientError("Aucune clé API Binance configurée.")

    path = "/fapi/v2/account" if config.market_type == "futures" else "/api/v3/account"
    data = _signed_rest_get(
        creds["api_key"],
        creds["api_secret"],
        path,
        market_type=config.market_type,
        testnet=bool(creds.get("testnet", True)),
    )
    if isinstance(data, dict) and ("balances" in data or "assets" in data or "totalWalletBalance" in data):
        return True

    client = _client_for_user(user_id, market_type=config.market_type)
    try:
        if config.market_type == "futures":
            client.futures_account()
        else:
            client.get_account()
        return True
    except BinanceAPIException as e:
        mark_credentials_invalid(user_id, str(e))
        raise BinanceClientError(f"Connexion Binance échouée : {e.message}")
    except Exception as e:
        raise BinanceClientError(f"Connexion Binance échouée : {e}")


def get_full_account_info(user_id: int, market_type: MarketType = "futures") -> dict:
    """
    Récupère toutes les informations du compte Binance strictement pour le market_type configuré :
    - Solde total (USDT + actifs)
    - Détail des actifs
    - Positions ouvertes + PnL non réalisé
    - Taux d'utilisation de la marge (Futures)
    Ne bascule jamais silencieusement entre Spot et Futures.
    """
    if market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché non supporté : {market_type}")

    creds = get_binance_credentials(user_id, market_type=market_type)
    if not creds or not creds.get("api_key") or not creds.get("api_secret"):
        raise BinanceClientError("Aucune clé API Binance configurée. Utilise /setapikeys pour les ajouter.")

    summary = {
        "market_type": market_type,
        "total_wallet_balance": 0.0,
        "available_balance": 0.0,
        "unrealized_pnl": 0.0,
        "margin_used_pct": 0.0,
        "assets": [],
        "positions": [],
        "recent_trades": [],
        "total_commissions": 0.0,
    }

    def _populate_futures(acc_data: dict, pos_data: list) -> None:
        summary["market_type"] = "futures"
        summary["total_wallet_balance"] = float(acc_data.get("totalWalletBalance", 0.0))
        summary["available_balance"] = float(acc_data.get("availableBalance", 0.0))
        summary["unrealized_pnl"] = float(acc_data.get("totalUnrealizedProfit", 0.0))

        total_maint_margin = float(acc_data.get("totalMaintMargin", 0.0))
        total_margin_balance = float(acc_data.get("totalMarginBalance", 1.0))
        if total_margin_balance > 0:
            summary["margin_used_pct"] = round((total_maint_margin / total_margin_balance) * 100, 2)

        for b in acc_data.get("assets", []):
            bal = float(b.get("walletBalance", 0.0))
            if bal > 0:
                summary["assets"].append({
                    "asset": b["asset"],
                    "wallet": bal,
                    "available": float(b.get("availableBalance", 0.0)),
                    "unrealized_pnl": float(b.get("unrealizedProfit", 0.0)),
                })

        for pos in (pos_data or []):
            amt = float(pos.get("positionAmt", 0.0))
            if amt != 0:
                entry = float(pos.get("entryPrice", 0.0))
                mark = float(pos.get("markPrice", 0.0))
                upnl = float(pos.get("unRealizedProfit", 0.0))
                side = "BUY (LONG)" if amt > 0 else "SELL (SHORT)"
                summary["positions"].append({
                    "symbol": pos["symbol"],
                    "side": side,
                    "quantity": abs(amt),
                    "entry_price": entry,
                    "mark_price": mark,
                    "unrealized_pnl": upnl,
                    "leverage": int(pos.get("leverage", 1)),
                    "liquidation_price": float(pos.get("liquidationPrice", 0.0)),
                })

    def _populate_spot(acc_data: dict) -> None:
        summary["market_type"] = "spot"
        balances = acc_data.get("balances", [])
        total_usdt = 0.0
        usdt_free = 0.0

        prices_map = {}
        try:
            r = requests.get("https://data-api.binance.vision/api/v3/ticker/price", timeout=5)
            if r.status_code == 200:
                for item in r.json():
                    prices_map[item["symbol"]] = float(item["price"])
        except Exception:
            pass

        for b in balances:
            free = float(b.get("free", 0.0))
            locked = float(b.get("locked", 0.0))
            total = free + locked
            if total > 0:
                asset = b["asset"]
                if asset == "USDT":
                    usdt_free = free
                    usdt_val = total
                elif asset in ("USDC", "BUSD", "FDUSD"):
                    usdt_val = total
                else:
                    price = prices_map.get(f"{asset}USDT", 0.0)
                    usdt_val = total * price
                total_usdt += usdt_val
                summary["assets"].append({
                    "asset": asset,
                    "free": free,
                    "locked": locked,
                    "total": total,
                    "usdt_value": round(usdt_val, 2),
                })

        summary["assets"].sort(key=lambda x: x.get("usdt_value", 0), reverse=True)
        summary["total_wallet_balance"] = round(total_usdt, 2)
        summary["available_balance"] = round(usdt_free, 2)

    is_testnet = bool(creds.get("testnet", True))

    # 1. Essai direct REST signé strictement sur le marché demandé
    if market_type == "futures":
        f_acc = _signed_rest_get(creds["api_key"], creds["api_secret"], "/fapi/v2/account", market_type="futures", testnet=is_testnet)
        if isinstance(f_acc, dict) and ("assets" in f_acc or "totalWalletBalance" in f_acc):
            f_pos = _signed_rest_get(creds["api_key"], creds["api_secret"], "/fapi/v2/positionRisk", market_type="futures", testnet=is_testnet)
            _populate_futures(f_acc, f_pos if isinstance(f_pos, list) else [])
            return summary
    else:
        s_acc = _signed_rest_get(creds["api_key"], creds["api_secret"], "/api/v3/account", market_type="spot", testnet=is_testnet)
        if isinstance(s_acc, dict) and "balances" in s_acc:
            _populate_spot(s_acc)
            return summary

    # 2. Fallback sur le client python-binance strictement sur le marché demandé
    client = _client_for_user(user_id, market_type=market_type)
    try:
        if market_type == "futures":
            acc = client.futures_account()
            raw_positions = client.futures_position_information()
            _populate_futures(acc, raw_positions)
        else:
            acc = client.get_account()
            _populate_spot(acc)
    except BinanceAPIException as e:
        if getattr(e, "code", None) in (-2015, -2014):
            mark_credentials_invalid(user_id, str(e))
        raise BinanceClientError(f"Erreur API Binance Account: {e.message}")
    except Exception as e:
        raise BinanceClientError(f"Erreur API Binance Account: {e}")

    return summary
