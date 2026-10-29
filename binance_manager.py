"""
binance_manager.py
-------------------
Encapsule toute la communication avec l'API Binance (spot + futures).
Ne jamais logguer api_key / api_secret en clair (voir trading_logger.py).

Dépendance : pip install python-binance
"""

import logging
import os
import threading
import hashlib
import hmac
import math
import time
import urllib.parse
import uuid
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Literal

import pandas as pd
import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

from trading_config import get_binance_credentials, mark_credentials_invalid, get_config
from trading_safety import SafetyError, assert_trading_allowed, engage_safe_mode
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


class BinancePositionNotFound(BinanceClientError):
    """Refus métier (et non erreur réseau/API) : aucune position Binance correspondante à fermer."""


class BinanceAlgoError(BinanceClientError):
    """Erreur renvoyée par l'API Algo Order de Binance (porte le code Binance, ex. -2021, -4130)."""

    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.code = code


# ---------------------------------------------------------------------------
# API « Algo Order » (ordres conditionnels Futures USDⓈ-M)
# ---------------------------------------------------------------------------
# Depuis fin 2025, Binance refuse STOP_MARKET / TAKE_PROFIT_MARKET / STOP / TAKE_PROFIT /
# TRAILING_STOP_MARKET sur POST /fapi/v1/order (erreur -4120 « use Algo Order API »).
# Ils doivent passer par POST /fapi/v1/algoOrder (algoType=CONDITIONAL, triggerPrice au lieu de stopPrice).
# Les helpers ci-dessous exposent des dicts « normalisés » (orderId, type, stopPrice, closePosition, algo=True)
# compatibles avec le reste du code, qui raisonne en orderId/stopPrice.

_ALGO_MAX_ATTEMPTS = 3
CONDITIONAL_ORDER_TYPES = {"STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT", "TRAILING_STOP_MARKET"}


def _client_rest_creds(client) -> tuple[str, str, bool]:
    key = getattr(client, "API_KEY", None)
    secret = getattr(client, "API_SECRET", None)
    if not key or not secret:
        raise BinanceClientError("Clés API indisponibles pour l'API Algo Binance.")
    return str(key), str(secret), bool(getattr(client, "testnet", False))


def _bool_str(v) -> str:
    return "true" if v else "false"


def _futures_algo_request(client, method: str, path: str, params: Optional[dict] = None) -> dict | list:
    """Requête signée vers l'API Futures avec retries sur erreurs transitoires (réseau, 5xx, 429, -1021)."""
    api_key, api_secret, testnet = _client_rest_creds(client)
    base = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
    last_err: Exception = BinanceAlgoError("Erreur réseau Binance (Algo)")
    for attempt in range(_ALGO_MAX_ATTEMPTS):
        q = {k: v for k, v in (params or {}).items() if v is not None}
        q["timestamp"] = int(time.time() * 1000)
        q.setdefault("recvWindow", 10000)
        query_str = urllib.parse.urlencode(q)
        sig = hmac.new(api_secret.encode("utf-8"), query_str.encode("utf-8"), hashlib.sha256).hexdigest()
        try:
            r = requests.request(
                method.upper(), f"{base}{path}?{query_str}&signature={sig}",
                headers={"X-MBX-APIKEY": api_key}, timeout=8,
            )
        except requests.RequestException as exc:
            last_err = BinanceAlgoError(f"Erreur réseau Binance (Algo) : {exc}")
            time.sleep(0.4 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()
        code, msg = None, r.text[:200]
        try:
            body = r.json()
            code, msg = body.get("code"), body.get("msg")
        except Exception:
            pass
        err = BinanceAlgoError(f"Code {code}: {msg}" if code is not None else f"HTTP {r.status_code}: {msg}", code=code)
        if r.status_code >= 500 or r.status_code == 429 or code == -1021:
            last_err = err
            time.sleep(0.4 * (attempt + 1))
            continue
        raise err
    raise last_err


def _normalize_algo_order(o: dict) -> dict:
    """Convertit une réponse Algo Binance au format « ordre classique » utilisé par le reste du code."""
    algo_id = o.get("algoId")
    status = str(o.get("algoStatus") or "NEW").upper()
    trigger = o.get("triggerPrice")
    otype = str(o.get("orderType") or o.get("type") or "").upper()
    return {
        "orderId": algo_id,
        "algoId": algo_id,
        "clientOrderId": o.get("clientAlgoId"),
        "clientAlgoId": o.get("clientAlgoId"),
        "symbol": o.get("symbol"),
        "side": o.get("side"),
        "type": otype,
        "origType": otype,
        "stopPrice": trigger,
        "triggerPrice": trigger,
        "closePosition": str(o.get("closePosition", "")).lower() in ("true", "1"),
        "reduceOnly": str(o.get("reduceOnly", "")).lower() in ("true", "1"),
        "workingType": o.get("workingType"),
        "status": "NEW" if status in ("NEW", "WORKING") else status,
        "algoStatus": status,
        "actualOrderId": o.get("actualOrderId"),
        "algo": True,
    }


def futures_place_conditional_order(
    client,
    symbol: str,
    side: str,
    order_type: str,
    trigger_price: str,
    *,
    close_position: bool = True,
    quantity: Optional[str] = None,
    working_type: str = "MARK_PRICE",
    client_algo_id: Optional[str] = None,
) -> dict:
    """Place un ordre conditionnel (SL/TP) via POST /fapi/v1/algoOrder. `trigger_price` doit être une chaîne
    déjà formatée au tick du symbole (jamais de float : notation scientifique rejetée par Binance)."""
    order_type = str(order_type).upper()
    if order_type not in CONDITIONAL_ORDER_TYPES:
        raise BinanceClientError(f"Type d'ordre conditionnel non supporté : {order_type}")
    params: dict = {
        "algoType": "CONDITIONAL",
        "symbol": normalize_symbol(symbol),
        "side": side.upper(),
        "type": order_type,
        "triggerPrice": str(trigger_price),
        "workingType": working_type,
        "clientAlgoId": client_algo_id,
    }
    if close_position:
        params["closePosition"] = "true"
    else:
        params["quantity"] = quantity
        params["reduceOnly"] = "true"
    res = _futures_algo_request(client, "POST", "/fapi/v1/algoOrder", params)
    if not isinstance(res, dict) or res.get("algoId") is None:
        raise BinanceAlgoError(f"Réponse inattendue de Binance (algoOrder) : {res}")
    out = _normalize_algo_order(res)
    out.setdefault("stopPrice", str(trigger_price))
    if not out.get("stopPrice"):
        out["stopPrice"] = str(trigger_price)
    out["closePosition"] = bool(close_position)
    return out


def futures_list_conditional_orders(client, symbol: Optional[str] = None) -> list[dict]:
    """Ordres conditionnels ouverts (SL/TP) — non visibles via futures_get_open_orders depuis la migration Algo."""
    try:
        params = {"symbol": normalize_symbol(symbol)} if symbol else None
        res = _futures_algo_request(client, "GET", "/fapi/v1/openAlgoOrders", params)
    except Exception as e:
        logger.warning("Liste des ordres Algo ouverts impossible (%s) : %s", symbol or "tous", e)
        return []
    if not isinstance(res, list):
        return []
    return [_normalize_algo_order(o) for o in res if isinstance(o, dict)]


def futures_cancel_conditional_order(client, symbol: str, order_id) -> bool:
    """Annule un ordre conditionnel par algoId. Retourne True si annulé."""
    _futures_algo_request(client, "DELETE", "/fapi/v1/algoOrder", {"symbol": normalize_symbol(symbol), "algoId": str(order_id)})
    return True


def futures_cancel_all_conditional_orders(client, symbol: str) -> None:
    _futures_algo_request(client, "DELETE", "/fapi/v1/algoOpenOrders", {"symbol": normalize_symbol(symbol)})


def futures_get_order_or_algo(client, symbol: str, order_id) -> Optional[dict]:
    """Retourne l'ordre (classique, sinon ordre d'exécution lié à un ordre Algo déclenché)."""
    symbol = normalize_symbol(symbol)
    try:
        return client.futures_get_order(symbol=symbol, orderId=order_id)
    except Exception:
        pass
    try:
        algo = _futures_algo_request(client, "GET", "/fapi/v1/algoOrder", {"algoId": str(order_id)})
        if isinstance(algo, dict):
            actual = algo.get("actualOrderId")
            if actual not in (None, "", 0, "0"):
                try:
                    return client.futures_get_order(symbol=symbol, orderId=actual)
                except Exception:
                    return None
    except Exception:
        return None
    return None


def get_mark_price(client, symbol: str) -> Optional[float]:
    """Mark price Futures (prix de déclenchement des SL/TP). None si indisponible."""
    symbol = normalize_symbol(symbol)
    try:
        data = client.futures_mark_price(symbol=symbol)
        if isinstance(data, list):
            data = next((d for d in data if d.get("symbol") == symbol), None)
        if isinstance(data, dict) and data.get("markPrice"):
            return float(data["markPrice"])
    except Exception:
        pass
    return None


def rebase_protective_levels(
    direction: str,
    planned_entry: Optional[float],
    fill_price: Optional[float],
    sl_price: Optional[float],
    tp_price: Optional[float],
    max_shift_pct: float = 1.5,
) -> tuple[Optional[float], Optional[float]]:
    """Décale SL/TP du même écart que le slippage (prix réel d'exécution - prix prévu).

    Les SL/TP viennent d'une analyse faite sur un prix un peu ancien : au moment du remplissage au marché le
    prix a bougé. Sans réalignement, les distances SL/TP (donc le risque et le R:R) changent, et un SL/TP trop
    proche peut être refusé (-2021 « would immediately trigger »). On conserve les distances d'origine.
    """
    try:
        if not planned_entry or not fill_price or planned_entry <= 0 or fill_price <= 0:
            return sl_price, tp_price
        delta = float(fill_price) - float(planned_entry)
        if delta == 0:
            return sl_price, tp_price
        # Écart anormal (signal périmé, prix très différent) : ce n'est plus du slippage, on ne déplace rien.
        if abs(delta) / float(planned_entry) * 100.0 > max_shift_pct:
            logger.warning(
                "Écart fill/entrée prévue trop grand (%.2f%% > %.2f%%) : SL/TP non recalés.",
                abs(delta) / float(planned_entry) * 100.0, max_shift_pct,
            )
            return sl_price, tp_price
        new_sl = float(sl_price) + delta if sl_price else sl_price
        new_tp = float(tp_price) + delta if tp_price else tp_price
        d = direction.upper()
        # Garde-fou : le décalage ne doit jamais inverser l'ordre SL / entrée / TP
        if d == "BUY":
            if (new_sl and new_sl >= fill_price) or (new_tp and new_tp <= fill_price):
                return sl_price, tp_price
        else:
            if (new_sl and new_sl <= fill_price) or (new_tp and new_tp >= fill_price):
                return sl_price, tp_price
        return new_sl, new_tp
    except (TypeError, ValueError):
        return sl_price, tp_price


ORDER_CONTEXT_AUTOTRADE = "autotrade"
ORDER_CONTEXT_MANUAL_AUTHENTICATED = "manual_authenticated"
ORDER_CONTEXT_EMERGENCY = "emergency_stop"
_ALLOWED_ORDER_CONTEXTS = {
    ORDER_CONTEXT_AUTOTRADE,
    ORDER_CONTEXT_MANUAL_AUTHENTICATED,
    ORDER_CONTEXT_EMERGENCY,
}


def _assert_order_context_allowed(
    user_id: int,
    execution_context: Optional[str],
    *,
    require_auto_trade: bool,
    allow_under_safety_lock: bool = False,
) -> None:
    """Fail closed before any real Binance order can be sent.

    Telegram/webhooks/scanners must not rely on their route-level checks only: every
    backend order primitive must receive an explicit, already-authorized execution
    context. AutoTrade contexts do not require a fresh PIN per order, but they are
    accepted only while AutoTrade remains enabled and safety state is valid.
    Note: Closing an existing position or cancelling orders reduces risk and is
    allowed for authenticated manual/emergency actions even if safety_lock is active.
    """
    if execution_context not in _ALLOWED_ORDER_CONTEXTS:
        raise BinanceClientError("Ordre réel refusé: contexte d'exécution non autorisé.")

    config = get_config(user_id)
    if not (allow_under_safety_lock and execution_context in (ORDER_CONTEXT_MANUAL_AUTHENTICATED, ORDER_CONTEXT_EMERGENCY)):
        try:
            assert_trading_allowed(
                config,
                require_auto_trade=(require_auto_trade or execution_context == ORDER_CONTEXT_AUTOTRADE),
            )
        except SafetyError as e:
            raise BinanceClientError(f"Ordre réel refusé: {e}")
    elif require_auto_trade or execution_context == ORDER_CONTEXT_AUTOTRADE:
        if not config.auto_trade:
            raise BinanceClientError("Ordre automatique refusé: AutoTrade est désactivé.")

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


def _fetch_klines_dataframe(
    symbol: str,
    timeframe: str,
    market_type: MarketType = "futures",
    limit: int = 500,
) -> Optional[pd.DataFrame]:
    """Fetch public Binance OHLCV data as a DataFrame compatible with SignalEngine (sans cache).
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



# Cache partagé de bougies (toutes les utilisateurs/symboles) : avec 10 cryptos + l'or, un scan par utilisateur
# multiplierait les appels REST. Durée courte (15 s par défaut, 0 = désactivé) : les bougies clôturées ne changent
# pas, et le prix temps réel reste lu séparément (jamais depuis ce cache).
KLINES_CACHE_TTL_SECONDS = float(os.environ.get("KLINES_CACHE_TTL_SECONDS", "15"))
_KLINES_CACHE: dict = {}
_KLINES_CACHE_LOCK = threading.Lock()
_KLINES_CACHE_MAX_ENTRIES = 300


def get_klines_dataframe(
    symbol: str,
    timeframe: str,
    market_type: MarketType = "futures",
    limit: int = 500,
) -> Optional[pd.DataFrame]:
    """Bougies Binance publiques avec micro-cache partagé. Retourne toujours une COPIE (l'appelant peut la modifier)."""
    ttl = KLINES_CACHE_TTL_SECONDS
    if ttl <= 0:
        return _fetch_klines_dataframe(symbol, timeframe, market_type, limit)
    key = (normalize_symbol(symbol), timeframe, market_type, int(limit))
    now = time.time()
    with _KLINES_CACHE_LOCK:
        hit = _KLINES_CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1].copy()
    df = _fetch_klines_dataframe(symbol, timeframe, market_type, limit)
    if df is not None and not df.empty:  # un échec n'est jamais mis en cache
        with _KLINES_CACHE_LOCK:
            if len(_KLINES_CACHE) >= _KLINES_CACHE_MAX_ENTRIES:
                for k in sorted(_KLINES_CACHE, key=lambda k: _KLINES_CACHE[k][0])[: _KLINES_CACHE_MAX_ENTRIES // 3]:
                    _KLINES_CACHE.pop(k, None)
            _KLINES_CACHE[key] = (now, df.copy())
    return df


def make_client_order_id(prefix: str, unique_key: Optional[str] = None, max_len: int = 36) -> str:
    """Build a Binance-compatible client order id (UUID-based when unique_key is omitted)."""
    safe_prefix = "".join(ch for ch in prefix if ch.isalnum() or ch in "_-")[:8] or "ord"
    if not unique_key:
        token = uuid.uuid4().hex[:24]
    else:
        raw = str(unique_key).strip()
        if len(raw) == 32 and all(c in "0123456789abcdefABCDEF" for c in raw):
            token = raw.lower()[:24]
        else:
            token = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{safe_prefix}_{token}"[:max_len]


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

    # Fallback historique UNIQUEMENT pour BTC/ETH/XAU. Pour tout autre symbole, un tick/step inventé serait faux
    # (ex. DOGE/XRP/ADA) : on refuse plutôt que d'envoyer un ordre avec une précision erronée.
    from config import LEGACY_FALLBACK_SYMBOLS
    if symbol not in LEGACY_FALLBACK_SYMBOLS:
        raise BinanceClientError(
            f"Filtres Binance (lot/tick) indisponibles pour {symbol} : exchangeInfo injoignable. "
            f"Ordre refusé pour éviter une quantité ou un prix invalide."
        )
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


def _place_futures_protective_orders(
    client: Client,
    symbol: str,
    opposite_side: str,
    sl_price: Optional[float],
    tp_price: Optional[float],
    filters: dict,
    warnings: Optional[list] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Annule les protections en conflit puis pose SL (STOP_MARKET) / TP (TAKE_PROFIT_MARKET) via l'API Algo.

    - Prix toujours envoyés en chaîne formatée au tick du symbole.
    - Déclenchement sur MARK_PRICE.
    - SL : obligatoire (une erreur remonte à l'appelant, qui ferme la position par sécurité).
    - TP : si Binance répond -2021 (« would immediately trigger », le prix a déjà atteint le TP), on le décale
      une fois juste au-delà du mark price ; si ça échoue encore, la position reste protégée par son SL et un
      avertissement est ajouté à `warnings`.
    """
    if sl_price or tp_price:
        target_types = set()
        if sl_price:
            target_types.add("STOP_MARKET")
        if tp_price:
            target_types.add("TAKE_PROFIT_MARKET")
        _cancel_conflicting_futures_protective_orders(
            client,
            symbol,
            side=opposite_side,
            order_types=target_types,
        )
    sl_oid: Optional[str] = None
    tp_oid: Optional[str] = None
    try:
        tick = float(filters.get("PRICE_FILTER", {}).get("tickSize", "0.01") or 0.01)
    except (TypeError, ValueError):
        tick = 0.01
    is_long_position = opposite_side == "SELL"  # on place l'ordre de sortie : SELL => position LONG

    if sl_price:
        sl_order = futures_place_conditional_order(
            client, symbol, opposite_side, "STOP_MARKET", format_price_for_symbol(sl_price, filters),
        )
        sl_oid = str(sl_order.get("orderId")) if sl_order.get("orderId") is not None else None

    if tp_price:
        trigger = float(tp_price)
        for attempt in range(2):
            try:
                tp_order = futures_place_conditional_order(
                    client, symbol, opposite_side, "TAKE_PROFIT_MARKET", format_price_for_symbol(trigger, filters),
                )
                tp_oid = str(tp_order.get("orderId")) if tp_order.get("orderId") is not None else None
                break
            except BinanceAlgoError as e:
                if e.code == -2021:
                    if attempt == 0:
                        mark = get_mark_price(client, symbol)
                        if mark:
                            buffer = max(mark * 0.0005, 2 * tick)
                            trigger = max(trigger, mark + buffer) if is_long_position else min(trigger, mark - buffer)
                        continue
                    msg = (
                        f"TP non posé sur {symbol} : le prix a déjà atteint le niveau cible (Binance -2021). "
                        f"La position reste protégée par son Stop Loss."
                    )
                    logger.warning(msg)
                    if warnings is not None:
                        warnings.append(msg)
                    break
                raise
    return (sl_oid, tp_oid)


def _place_spot_oco_order(
    client: Client,
    symbol: str,
    opposite_side: str,
    quantity: float,
    sl_price: float,
    tp_price: float,
    filters: dict,
) -> tuple[Optional[str], Optional[str], dict]:
    """Place a Spot OCO order (take-profit limit + stop-loss) and extract (sl_order_id, tp_order_id, raw_oco)."""
    tp_str = format_price_for_symbol(tp_price, filters)
    sl_stop_str = format_price_for_symbol(sl_price, filters)
    tick_size = float(filters.get("PRICE_FILTER", {}).get("tickSize", "0.01") or 0.01)
    if opposite_side == "SELL":
        stop_limit_val = max(float(sl_price) * 0.998, float(sl_price) - max(tick_size * 2, 1e-8), tick_size)
    else:
        stop_limit_val = float(sl_price) * 1.002 + max(tick_size * 2, 1e-8)
    sl_limit_str = format_price_for_symbol(stop_limit_val, filters)
    oco = client.create_oco_order(
        symbol=symbol,
        side=opposite_side,
        quantity=quantity,
        price=tp_str,
        stopPrice=sl_stop_str,
        stopLimitPrice=sl_limit_str,
        stopLimitTimeInForce="GTC",
    )
    sl_oid: Optional[str] = None
    tp_oid: Optional[str] = None
    if isinstance(oco, dict):
        reports = oco.get("orderReports") or []
        for rep in reports:
            if not isinstance(rep, dict):
                continue
            rtype = str(rep.get("type", "")).upper()
            oid = rep.get("orderId")
            if oid is None:
                continue
            if "STOP" in rtype:
                sl_oid = str(oid)
            elif "LIMIT" in rtype or "MAKER" in rtype:
                tp_oid = str(oid)
        if (not sl_oid or not tp_oid) and isinstance(oco.get("orders"), list):
            orders_list = oco["orders"]
            if len(orders_list) >= 1 and not sl_oid and orders_list[0].get("orderId") is not None:
                sl_oid = str(orders_list[0]["orderId"])
            if len(orders_list) >= 2 and not tp_oid and orders_list[1].get("orderId") is not None:
                tp_oid = str(orders_list[1]["orderId"])
        if not sl_oid and oco.get("orderListId") is not None:
            sl_oid = str(oco["orderListId"])
        if not tp_oid and oco.get("orderListId") is not None:
            tp_oid = str(oco["orderListId"])
    return sl_oid, tp_oid, oco if isinstance(oco, dict) else {}


def _lookup_order_by_client_id(
    client: Client,
    symbol: str,
    client_order_id: str,
    market_type: MarketType,
) -> Optional[dict]:
    """Query an order on Binance by origClientOrderId after a network/timeout error."""
    if not client_order_id:
        return None
    try:
        if market_type == "futures" and hasattr(client, "futures_get_order"):
            return client.futures_get_order(symbol=symbol, origClientOrderId=client_order_id)
        if market_type == "spot" and hasattr(client, "get_order"):
            return client.get_order(symbol=symbol, origClientOrderId=client_order_id)
    except Exception as exc:
        logger.debug("Order lookup by clientOrderId=%s (%s) failed: %s", client_order_id, symbol, exc)
    return None


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
    planned_entry_price: Optional[float] = None,
) -> dict:
    """
    Ouvre une position au marché, puis place SL/TP (recalés sur le prix réel d'exécution si `planned_entry_price`
    est fourni, pour conserver les distances / le risque / le R:R prévus malgré le slippage).
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

    if not client_order_id:
        client_order_id = make_client_order_id("ord", uuid.uuid4().hex)

    opened_order: Optional[dict] = None
    main_order_sent = False
    opposite = "SELL" if direction == "BUY" else "BUY"
    filters: dict = {}
    result: dict = {"quantity": quantity, "executed_price": None, "client_order_id": client_order_id}

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

        result = {"quantity": quantity, "executed_price": None, "client_order_id": client_order_id}

        if market_type == "futures":
            if leverage:
                set_leverage(user_id, symbol, int(leverage))

            order_params = {
                "symbol": symbol,
                "side": direction,
                "type": "MARKET",
                "quantity": quantity,
                "newClientOrderId": client_order_id,
            }
            main_order_sent = True
            order = client.futures_create_order(**order_params)
            opened_order = order
            result["order_id"] = order["orderId"]
            result["client_order_id"] = order.get("clientOrderId") or client_order_id
            result["executed_price"] = _extract_order_fill_price(order) or get_mark_price(client, symbol)

            # Réaligner SL/TP sur le prix réellement obtenu (slippage) : mêmes distances, même risque.
            if planned_entry_price and result["executed_price"]:
                new_sl, new_tp = rebase_protective_levels(
                    direction, planned_entry_price, result["executed_price"], sl_price, tp_price
                )
                if (new_sl, new_tp) != (sl_price, tp_price):
                    logger.info(
                        "SL/TP recalés sur le fill %s %s: entrée prévue=%s fill=%s SL %s->%s TP %s->%s",
                        symbol, direction, planned_entry_price, result["executed_price"],
                        sl_price, new_sl, tp_price, new_tp,
                    )
                sl_price, tp_price = new_sl, new_tp
            result["sl_price"] = sl_price
            result["tp_price"] = tp_price

            protect_warnings: list = []
            sl_oid, tp_oid = _place_futures_protective_orders(
                client, symbol, opposite, sl_price, tp_price, filters, warnings=protect_warnings
            )
            if protect_warnings:
                result["warnings"] = protect_warnings
            if sl_oid:
                result["sl_order_id"] = sl_oid
            if tp_oid:
                result["tp_order_id"] = tp_oid

        else:  # spot
            order_params = {
                "symbol": symbol,
                "side": direction,
                "type": "MARKET",
                "quantity": quantity,
                "newClientOrderId": client_order_id,
            }
            main_order_sent = True
            order = client.create_order(**order_params)
            opened_order = order
            result["order_id"] = order["orderId"]
            result["client_order_id"] = order.get("clientOrderId") or client_order_id
            result["executed_price"] = _extract_order_fill_price(order)
            result["sl_order_id"] = None
            result["tp_order_id"] = None
            if sl_price and tp_price:
                sl_oid, tp_oid, _ = _place_spot_oco_order(
                    client, symbol, opposite, quantity, float(sl_price), float(tp_price), filters
                )
                result["sl_order_id"] = sl_oid
                result["tp_order_id"] = tp_oid
            elif sl_price or tp_price:
                raise BinanceClientError("Spot requiert sl_price et tp_price pour poser un ordre OCO de protection.")

        return result

    except BinanceClientError:
        if not main_order_sent:
            raise
        err_after_send: Exception = BinanceOrderException("Protection Spot OCO manquante ou refusée")
    except Exception as e:
        err_after_send = e
        if getattr(e, "code", None) in (-2015, -2014):
            mark_credentials_invalid(user_id, str(e))
        if not main_order_sent:
            raise BinanceClientError(f"Erreur Binance à l'ouverture : {getattr(e, 'message', str(e))}")

    # Récupération sécurisée après erreur réseau / timeout / exception après envoi de l'ordre principal
    e = err_after_send
    if opened_order is None:
        opened_order = _lookup_order_by_client_id(client, symbol, client_order_id, market_type)
        if opened_order and opened_order.get("orderId") is not None:
            result["order_id"] = opened_order.get("orderId")
            result["client_order_id"] = opened_order.get("clientOrderId") or client_order_id
            result["executed_price"] = _extract_order_fill_price(opened_order)

    if market_type == "futures":
        remote_pos = None
        remote_check_ok = False
        try:
            positions = get_open_binance_positions(user_id, market_type="futures")
            remote_check_ok = True
            remote_pos = next(
                (p for p in (positions or []) if normalize_symbol(p.get("symbol", "")) == symbol and p.get("direction") == direction),
                None,
            )
        except Exception as pos_err:
            logger.warning("Vérification position après erreur sur %s (user=%s) impossible: %s", symbol, user_id, pos_err)

        order_filled = bool(
            opened_order
            and str(opened_order.get("status", "FILLED")).upper() in ("FILLED", "PARTIALLY_FILLED")
        ) or (opened_order is not None and "status" not in opened_order)

        if remote_pos is not None or order_filled:
            has_sl = bool(result.get("sl_order_id")) or not sl_price
            has_tp = bool(result.get("tp_order_id")) or not tp_price
            if not (has_sl and has_tp):
                try:
                    sl_oid, tp_oid = _place_futures_protective_orders(
                        client,
                        symbol,
                        opposite,
                        sl_price if not result.get("sl_order_id") else None,
                        tp_price if not result.get("tp_order_id") else None,
                        filters,
                    )
                    if sl_oid:
                        result["sl_order_id"] = sl_oid
                    if tp_oid:
                        result["tp_order_id"] = tp_oid
                    has_sl = bool(result.get("sl_order_id")) or not sl_price
                    has_tp = bool(result.get("tp_order_id")) or not tp_price
                    if has_sl and has_tp and result.get("order_id") is not None:
                        return result
                except Exception as prot_err:
                    logger.warning("Échec pose protection de secours sur %s (user=%s): %s", symbol, user_id, prot_err)

            # Protection non confirmée -> fermeture d'urgence reduceOnly
            close_qty = float(remote_pos["quantity"]) if remote_pos and remote_pos.get("quantity") else quantity
            try:
                client.futures_create_order(
                    symbol=symbol,
                    side=opposite,
                    type="MARKET",
                    quantity=close_qty,
                    reduceOnly=True,
                )
            except Exception as close_error:
                reason = (
                    f"Position {symbol} potentiellement sans protection après erreur ({getattr(e, 'message', str(e))}) "
                    f"et échec fermeture reduceOnly ({close_error})"
                )
                logger.critical("SAFE_MODE triggered for user=%s: %s", user_id, reason)
                engage_safe_mode(user_id, reason)
                raise BinanceClientError(
                    "Ordre principal ouvert mais protection SL/TP échouée; "
                    "fermeture automatique impossible. Safe Mode activé."
                )
            raise BinanceClientError(
                "Ordre principal ouvert puis refermé car la protection SL/TP a échoué."
            )

        if not remote_check_ok and opened_order is None:
            reason = f"État d'ordre incertain après erreur réseau sur {symbol} (clientOrderId={client_order_id}): {e}"
            engage_safe_mode(user_id, reason)
            raise BinanceClientError(f"Erreur réseau sur {symbol}; état incertain, Safe Mode activé.")
        raise BinanceClientError(f"Erreur Binance à l'ouverture : {getattr(e, 'message', str(e))}")

    else:  # spot
        order_filled = bool(
            opened_order
            and str(opened_order.get("status", "FILLED")).upper() in ("FILLED", "PARTIALLY_FILLED")
        ) or (opened_order is not None and "status" not in opened_order)

        if order_filled:
            if sl_price and tp_price and not (result.get("sl_order_id") and result.get("tp_order_id")):
                try:
                    sl_oid, tp_oid, _ = _place_spot_oco_order(
                        client, symbol, opposite, quantity, float(sl_price), float(tp_price), filters
                    )
                    result["sl_order_id"] = sl_oid
                    result["tp_order_id"] = tp_oid
                    if result.get("order_id") is not None and sl_oid and tp_oid:
                        return result
                except Exception as oco_err:
                    logger.warning("Échec pose OCO Spot sur %s (user=%s): %s", symbol, user_id, oco_err)

            # Impossible de poser l'OCO -> fermer la position Spot au marché et lever une erreur
            try:
                client.create_order(
                    symbol=symbol,
                    side="SELL",
                    type="MARKET",
                    quantity=quantity,
                )
            except Exception as close_error:
                reason = (
                    f"Position Spot {symbol} sans protection OCO après erreur ({getattr(e, 'message', str(e))}) "
                    f"et échec revente marché ({close_error})"
                )
                logger.critical("SAFE_MODE triggered for user=%s: %s", user_id, reason)
                engage_safe_mode(user_id, reason)
                raise BinanceClientError(
                    "Achat Spot exécuté mais protection OCO échouée; revente automatique impossible. Safe Mode activé."
                )
            raise BinanceClientError(
                "Achat Spot exécuté puis revendu au marché car la pose de la protection OCO a échoué."
            )

        if opened_order is None:
            reason = f"État d'ordre Spot incertain après erreur réseau sur {symbol} (clientOrderId={client_order_id}): {e}"
            engage_safe_mode(user_id, reason)
            raise BinanceClientError(f"Erreur réseau Spot sur {symbol}; état incertain, Safe Mode activé.")
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
    creds = get_binance_credentials(user_id, market_type="futures")
    if creds and creds.get("api_key") and creds.get("api_secret"):
        rest_pos = _signed_rest_get(
            creds["api_key"],
            creds["api_secret"],
            "/fapi/v2/positionRisk",
            market_type="futures",
            testnet=bool(creds.get("testnet", True)),
        )
        if isinstance(rest_pos, list):
            positions = []
            for pos in rest_pos:
                amt = float(pos.get("positionAmt", 0.0))
                if amt == 0:
                    continue
                positions.append({
                    "symbol": normalize_symbol(pos["symbol"]),
                    "direction": "BUY" if amt > 0 else "SELL",
                    "quantity": abs(amt),
                    "entry_price": float(pos.get("entryPrice", 0.0)),
                    "mark_price": float(pos.get("markPrice", 0.0)),
                    "unrealized_pnl": float(pos.get("unRealizedProfit", 0.0)),
                    "leverage": int(pos.get("leverage", 1)),
                })
            return positions

    client = _client_for_user(user_id, market_type="futures")
    try:
        positions = []
        for pos in client.futures_position_information():
            amt = float(pos.get("positionAmt", 0.0))
            if amt == 0:
                continue
            positions.append({
                "symbol": normalize_symbol(pos["symbol"]),
                "direction": "BUY" if amt > 0 else "SELL",
                "quantity": abs(amt),
                "entry_price": float(pos.get("entryPrice", 0.0)),
                "mark_price": float(pos.get("markPrice", 0.0)),
                "unrealized_pnl": float(pos.get("unRealizedProfit", 0.0)),
                "leverage": int(pos.get("leverage", 1)),
            })
        return positions
    except BinanceAPIException as e:
        raise BinanceClientError(f"Erreur Binance (positions ouvertes) : {e.message}")


def get_open_binance_orders(user_id: int, market_type: MarketType = "futures", symbol: Optional[str] = None) -> list[dict]:
    """Return open Binance orders for reconciliation."""
    if market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché non supporté : {market_type}")
    creds = get_binance_credentials(user_id, market_type=market_type)
    if creds and creds.get("api_key") and creds.get("api_secret"):
        path = "/fapi/v1/openOrders" if market_type == "futures" else "/api/v3/openOrders"
        params = {"symbol": normalize_symbol(symbol)} if symbol else None
        rest_orders = _signed_rest_get(
            creds["api_key"],
            creds["api_secret"],
            path,
            params,
            market_type=market_type,
            testnet=bool(creds.get("testnet", True)),
        )
        if isinstance(rest_orders, list):
            if market_type == "futures":
                # SL/TP = ordres Algo depuis la migration Binance : on les ajoute pour que l'UI/la réconciliation les voient.
                rest_orders = rest_orders + futures_list_conditional_orders(_client_for_user(user_id, market_type="futures"), symbol)
            return rest_orders

    client = _client_for_user(user_id, market_type=market_type)
    try:
        if market_type == "futures":
            base_orders = client.futures_get_open_orders(symbol=symbol) if symbol else client.futures_get_open_orders()
            return list(base_orders) + futures_list_conditional_orders(client, symbol)
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

    _assert_order_context_allowed(
        user_id,
        execution_context,
        require_auto_trade=(execution_context == ORDER_CONTEXT_AUTOTRADE),
        allow_under_safety_lock=True,
    )
    client = _client_for_user(user_id, market_type=market_type)
    symbol = normalize_symbol(symbol).upper()
    direction = direction.upper()
    if market_type == "spot" and direction == "SELL":
        raise BinanceClientError("Fermeture d'une position SHORT impossible en mode Spot standard.")
    opposite = "SELL" if direction == "BUY" else "BUY"

    try:
        effective_qty = float(quantity)
        if market_type == "futures":
            remote_positions = get_open_binance_positions(user_id, market_type=market_type)
            exact_matching = [
                p for p in remote_positions
                if normalize_symbol(p["symbol"]) == symbol
                and p["direction"] == direction
                and abs(float(p["quantity"]) - float(quantity)) <= max(float(quantity) * 0.001, 1e-12)
            ]
            if exact_matching:
                effective_qty = float(exact_matching[0]["quantity"])
            else:
                same_dir = [
                    p for p in remote_positions
                    if normalize_symbol(p["symbol"]) == symbol and p["direction"] == direction
                ]
                if same_dir and execution_context in (ORDER_CONTEXT_MANUAL_AUTHENTICATED, ORDER_CONTEXT_EMERGENCY):
                    # L'utilisateur ferme manuellement ou en urgence : on ferme la quantité réellement ouverte (ou min)
                    effective_qty = float(same_dir[0]["quantity"]) if float(quantity) <= 0 else min(float(quantity), float(same_dir[0]["quantity"]))
                elif same_dir and execution_context == ORDER_CONTEXT_AUTOTRADE:
                    # AutoTrade : la position correspondante existe mais sa quantité diffère de la quantité locale
                    # (réduction partielle, arrondi, fusion One-Way…). On ferme la quantité RÉELLEMENT présente.
                    effective_qty = float(same_dir[0]["quantity"])
                    logger.warning(
                        "close_position AUTOTRADE %s %s: quantité locale %s != quantité Binance %s, fermeture de la quantité Binance.",
                        symbol, direction, quantity, effective_qty,
                    )
                else:
                    raise BinancePositionNotFound(
                        f"Fermeture refusée: aucune position Binance {symbol} {direction} "
                        f"avec quantité attendue {quantity}."
                    )
        try:
            filters = get_symbol_filters(client, symbol, market_type)
        except BinanceClientError:
            filters = {}  # Fermeture = réduction de risque : on tente avec la quantité brute plutôt que de bloquer.
        if filters:
            step_size = filters.get("LOT_SIZE", {}).get("stepSize") or filters.get("MARKET_LOT_SIZE", {}).get("stepSize", "0.001")
            qty = format_step_value(effective_qty, step_size)
            if float(qty) <= 0:
                qty = str(effective_qty)
        else:
            qty = str(effective_qty)
        if market_type == "futures":
            try:
                order = client.futures_create_order(
                    symbol=symbol, side=opposite, type="MARKET",
                    quantity=qty, reduceOnly=True,
                )
            except (BinanceAPIException, BinanceOrderException):
                raise
            except Exception:
                creds = get_binance_credentials(user_id, market_type="futures")
                if not creds:
                    raise
                order = _signed_rest_request(
                    "POST",
                    creds["api_key"],
                    creds["api_secret"],
                    "/fapi/v1/order",
                    {
                        "symbol": symbol,
                        "side": opposite,
                        "type": "MARKET",
                        "quantity": qty,
                        "reduceOnly": "true",
                    },
                    market_type="futures",
                    testnet=bool(creds.get("testnet", True)),
                )
        else:
            try:
                order = client.create_order(
                    symbol=symbol, side=opposite, type="MARKET", quantity=qty
                )
            except (BinanceAPIException, BinanceOrderException):
                raise
            except Exception:
                creds = get_binance_credentials(user_id, market_type="spot")
                if not creds:
                    raise
                order = _signed_rest_request(
                    "POST",
                    creds["api_key"],
                    creds["api_secret"],
                    "/api/v3/order",
                    {
                        "symbol": symbol,
                        "side": opposite,
                        "type": "MARKET",
                        "quantity": qty,
                    },
                    market_type="spot",
                    testnet=bool(creds.get("testnet", True)),
                )
        return {
            "order_id": order.get("orderId") if isinstance(order, dict) else None,
            "executed_price": _extract_order_fill_price(order if isinstance(order, dict) else None),
            "closed_quantity": float(qty),
        }
    except (BinanceAPIException, BinanceOrderException) as e:
        if market_type == "futures" and getattr(e, "code", None) == -2022:
            # ReduceOnly rejeté : la position a disparu entre la lecture et l'ordre (déjà fermée) -> refus métier.
            raise BinancePositionNotFound(
                f"Fermeture refusée: position Binance {symbol} {direction} déjà fermée (reduceOnly rejeté)."
            )
        raise BinanceClientError(f"Erreur Binance à la fermeture : {getattr(e, 'message', str(e))}")


def cancel_order(user_id: int, symbol: str, order_id: str, market_type: MarketType = "futures", execution_context: Optional[str] = None, algo: Optional[bool] = None) -> None:
    _assert_order_context_allowed(
        user_id,
        execution_context,
        require_auto_trade=(execution_context == ORDER_CONTEXT_AUTOTRADE),
        allow_under_safety_lock=True,
    )
    client = _client_for_user(user_id, market_type=market_type)
    try:
        if market_type == "futures":
            if algo:
                futures_cancel_conditional_order(client, symbol, order_id)
            else:
                try:
                    client.futures_cancel_order(symbol=symbol, orderId=order_id)
                except Exception as classic_err:
                    # L'identifiant est peut-être celui d'un ordre Algo (SL/TP) : on tente l'annulation Algo.
                    try:
                        futures_cancel_conditional_order(client, symbol, order_id)
                    except Exception:
                        raise classic_err
        else:
            client.cancel_order(symbol=symbol, orderId=order_id)
    except Exception as e:
        # Non bloquant : l'ordre est peut-être déjà exécuté/annulé.
        logger.warning("Annulation ordre %s (%s) impossible : %s", order_id, symbol, getattr(e, "message", e))


def _find_futures_protective_orders(
    client: Client,
    symbol: str,
    side: Optional[str] = None,
    order_types: Optional[set[str]] = None,
    include_all_close_position: bool = False,
    user_id: Optional[int] = None,
) -> list[dict]:
    """Détecte les ordres protecteurs closePosition/reduceOnly déjà ouverts sur Binance Futures."""
    symbol = normalize_symbol(symbol)
    target_types = {t.upper() for t in (order_types or {"STOP_MARKET", "STOP", "TAKE_PROFIT_MARKET", "TAKE_PROFIT"})}
    open_orders: list = []
    if hasattr(client, "futures_get_open_orders"):
        try:
            open_orders = client.futures_get_open_orders(symbol=symbol) or []
        except Exception as e:
            logger.warning("Impossible de lister les ordres protecteurs ouverts sur %s (avec symbol): %s", symbol, e)
            try:
                open_orders = client.futures_get_open_orders() or []
            except Exception as e2:
                logger.warning("Impossible de lister les ordres protecteurs ouverts sur %s (sans symbol): %s", symbol, e2)
                open_orders = []

    if not open_orders and user_id is not None:
        try:
            creds = get_binance_credentials(user_id, market_type="futures")
            if creds and creds.get("api_key") and creds.get("api_secret"):
                rest_orders = _signed_rest_get(
                    creds["api_key"],
                    creds["api_secret"],
                    "/fapi/v1/openOrders",
                    {"symbol": symbol},
                    market_type="futures",
                    testnet=bool(creds.get("testnet", True)),
                )
                if isinstance(rest_orders, list):
                    open_orders = rest_orders
        except Exception:
            pass

    # Depuis la migration Algo de Binance, les SL/TP n'apparaissent plus dans openOrders : on les ajoute.
    open_orders = list(open_orders) + futures_list_conditional_orders(client, symbol)

    matched: list[dict] = []
    for o in open_orders:
        if not isinstance(o, dict):
            continue
        o_sym = normalize_symbol(str(o.get("symbol") or symbol))
        if o_sym != symbol:
            continue
        o_type = str(o.get("type") or o.get("origType") or o.get("orderType") or "").upper()
        if side and str(o.get("side") or "").upper() != side.upper():
            continue
        is_close_pos = str(o.get("closePosition", "")).lower() in ("true", "1") or bool(o.get("closePosition"))
        is_reduce_only = str(o.get("reduceOnly", "")).lower() in ("true", "1") or bool(o.get("reduceOnly"))
        if include_all_close_position and is_close_pos:
            matched.append(o)
            continue
        if o_type not in target_types:
            continue
        if is_close_pos or is_reduce_only or o_type in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "STOP", "TAKE_PROFIT"):
            matched.append(o)
    return matched


def _cancel_conflicting_futures_protective_orders(
    client: Client,
    symbol: str,
    side: Optional[str] = None,
    order_types: Optional[set[str]] = None,
    exclude_order_ids: Optional[set[str]] = None,
    include_all_close_position: bool = False,
    user_id: Optional[int] = None,
) -> list[str]:
    """Annule tous les ordres protecteurs closePosition en conflit avant d'en créer/remplacer un."""
    symbol = normalize_symbol(symbol)
    excluded = {str(oid) for oid in (exclude_order_ids or set()) if oid is not None}
    cancelled_ids: list[str] = []
    orders = _find_futures_protective_orders(
        client,
        symbol,
        side=side,
        order_types=order_types,
        include_all_close_position=include_all_close_position,
        user_id=user_id,
    )
    for o in orders:
        oid = o.get("orderId")
        orig_client_oid = o.get("clientOrderId")
        if oid is not None and str(oid) in excluded:
            continue
        cancelled = False
        if o.get("algo") and oid is not None:
            try:
                futures_cancel_conditional_order(client, symbol, oid)
                cancelled_ids.append(str(oid))
            except Exception as e:
                logger.warning("Annulation ordre Algo %s (%s) impossible : %s", oid, symbol, e)
            continue
        if oid is not None and hasattr(client, "futures_cancel_order"):
            for candidate_id in (oid, int(oid) if str(oid).isdigit() else oid, str(oid)):
                try:
                    client.futures_cancel_order(symbol=symbol, orderId=candidate_id)
                    cancelled_ids.append(str(oid))
                    cancelled = True
                    break
                except Exception as e:
                    logger.debug("Tentative annulation orderId=%s (%s) échouée : %s", candidate_id, symbol, e)
        if not cancelled and orig_client_oid and hasattr(client, "futures_cancel_order"):
            try:
                client.futures_cancel_order(symbol=symbol, origClientOrderId=str(orig_client_oid))
                cancelled_ids.append(str(oid or orig_client_oid))
                cancelled = True
            except Exception as e:
                logger.warning("Annulation ordre protecteur en conflit %s (%s) impossible : %s", oid or orig_client_oid, symbol, e)
        if not cancelled and user_id is not None and oid is not None:
            try:
                creds = get_binance_credentials(user_id, market_type="futures")
                if creds and creds.get("api_key") and creds.get("api_secret"):
                    _signed_rest_request(
                        "DELETE",
                        creds["api_key"],
                        creds["api_secret"],
                        "/fapi/v1/order",
                        {"symbol": symbol, "orderId": str(oid)},
                        market_type="futures",
                        testnet=bool(creds.get("testnet", True)),
                    )
                    cancelled_ids.append(str(oid))
            except Exception:
                pass
    return cancelled_ids


def _cancel_all_open_futures_orders_fallback(
    client: Client,
    symbol: str,
    preserve_tp_order: Optional[dict] = None,
    user_id: Optional[int] = None,
) -> None:
    """Purge d'urgence de tous les ordres ouverts du symbole si un ordre closePosition GTE/LTE fantôme bloque (-4130)."""
    symbol = normalize_symbol(symbol)
    purged = False
    try:
        futures_cancel_all_conditional_orders(client, symbol)
    except Exception as e:
        logger.warning("Annulation de tous les ordres Algo (%s) a échoué : %s", symbol, e)
    if hasattr(client, "futures_cancel_all_open_orders"):
        try:
            client.futures_cancel_all_open_orders(symbol=symbol)
            purged = True
        except Exception as e:
            logger.warning("futures_cancel_all_open_orders(%s) a échoué : %s", symbol, e)
    if not purged and user_id is not None:
        try:
            creds = get_binance_credentials(user_id, market_type="futures")
            if creds and creds.get("api_key") and creds.get("api_secret"):
                _signed_rest_request(
                    "DELETE",
                    creds["api_key"],
                    creds["api_secret"],
                    "/fapi/v1/allOpenOrders",
                    {"symbol": symbol},
                    market_type="futures",
                    testnet=bool(creds.get("testnet", True)),
                )
        except Exception as e:
            logger.warning("REST DELETE /fapi/v1/allOpenOrders(%s) a échoué : %s", symbol, e)


def _restore_preserved_tp_order_if_needed(
    client: Client,
    symbol: str,
    preserve_tp_order: Optional[dict] = None,
) -> None:
    """Recrée le TP préservé APRÈS que le nouveau SL ait été placé avec succès."""
    if not isinstance(preserve_tp_order, dict):
        return
    symbol = normalize_symbol(symbol)
    tp_stop = preserve_tp_order.get("stopPrice")
    tp_side = preserve_tp_order.get("side")
    tp_type = str(preserve_tp_order.get("type") or preserve_tp_order.get("origType") or "TAKE_PROFIT_MARKET").upper()
    if tp_stop and tp_side:
        try:
            futures_place_conditional_order(
                client,
                symbol,
                tp_side,
                "TAKE_PROFIT_MARKET",
                str(tp_stop),
            )
        except Exception as e:
            logger.debug("Restauration TP optionnelle ignorée sur %s : %s", symbol, e)


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
    if created_order.get("algo"):
        open_algo = futures_list_conditional_orders(client, symbol)
        if open_algo and new_oid not in {str(o.get("orderId")) for o in open_algo}:
            raise BinanceClientError(
                f"Confirmation SL/TP échouée sur {symbol}: le nouvel ordre #{new_oid} est absent des ordres Algo ouverts Binance."
            )
        return new_oid
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
    - Si un ordre STOP_MARKET existant a déjà exactement le même stopPrice formaté (ou meilleur), le conserve.
    - Annule les ordres STOP_MARKET en conflit (erreur -4130 closePosition GTE existant) et recrée immédiatement
      la protection dans le même flux atomique.
    - Si le prix de marché a dépassé le nouveau SL (ce qui amène Binance à interpréter le STOP_MARKET comme GTE
      et à entrer en conflit -4130 avec le TAKE_PROFIT_MARKET existant), conserve la protection existante sans lever d'erreur.
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
        order_types={"STOP_MARKET", "STOP", "TRAILING_STOP_MARKET"},
        user_id=user_id,
    )
    existing_tp_orders = _find_futures_protective_orders(
        client,
        symbol,
        side=opposite,
        order_types={"TAKE_PROFIT_MARKET", "TAKE_PROFIT"},
        user_id=user_id,
    )

    # Si un ordre STOP_MARKET actif possède déjà ce stopPrice exact (ou meilleur), éviter un appel de remplacement inutile
    for existing in existing_sl_orders:
        ex_id = existing.get("orderId")
        ex_stop = existing.get("stopPrice")
        try:
            if ex_id is not None and ex_stop is not None:
                ex_val = float(ex_stop)
                target_val = float(formatted_stop)
                is_same_or_better = (
                    abs(ex_val - target_val) <= 1e-9
                    or (direction.upper() == "BUY" and ex_val >= target_val - 1e-9)
                    or (direction.upper() == "SELL" and ex_val <= target_val + 1e-9)
                )
                if is_same_or_better:
                    _cancel_conflicting_futures_protective_orders(
                        client,
                        symbol,
                        side=opposite,
                        order_types={"STOP_MARKET", "STOP", "TRAILING_STOP_MARKET"},
                        exclude_order_ids={str(ex_id)},
                        user_id=user_id,
                    )
                    return str(ex_id)
        except (TypeError, ValueError):
            pass

    # Annuler d'abord l'ancien SL connu et tout autre STOP_MARKET closePosition en conflit
    ids_to_cancel: set[str] = set()
    if old_sl_order_id:
        ids_to_cancel.add(str(old_sl_order_id))
    for existing in existing_sl_orders:
        if existing.get("orderId") is not None:
            ids_to_cancel.add(str(existing["orderId"]))

    old_stop_price_fallback: Optional[str] = None
    old_sl_order_id_fallback: Optional[str] = str(old_sl_order_id) if old_sl_order_id else None
    for existing in existing_sl_orders:
        if existing.get("stopPrice") is not None:
            old_stop_price_fallback = str(existing["stopPrice"])
            if existing.get("orderId") is not None:
                old_sl_order_id_fallback = str(existing["orderId"])
            break

    for oid in ids_to_cancel:
        cancel_order(user_id, symbol, oid, "futures", execution_context=execution_context)
    _cancel_conflicting_futures_protective_orders(
        client,
        symbol,
        side=opposite,
        order_types={"STOP_MARKET", "STOP", "TRAILING_STOP_MARKET"},
        user_id=user_id,
    )

    try:
        sl_order = futures_place_conditional_order(
            client, symbol, opposite, "STOP_MARKET", formatted_stop,
        )
    except (BinanceAPIException, BinanceAlgoError) as e:
        msg = getattr(e, "message", str(e))
        if "closePosition" in msg or getattr(e, "code", None) == -4130:
            tp_to_preserve = existing_tp_orders[0] if existing_tp_orders else None
            _cancel_conflicting_futures_protective_orders(
                client,
                symbol,
                side=None,
                order_types={"STOP_MARKET", "STOP", "TRAILING_STOP_MARKET"},
                include_all_close_position=True,
                user_id=user_id,
            )
            try:
                sl_order = futures_place_conditional_order(
                    client, symbol, opposite, "STOP_MARKET", formatted_stop,
                )
            except Exception:
                # Dernier recours : purger l'ensemble des ordres ouverts du symbole sur Binance Futures,
                # créer le nouveau SL en priorité absolue, puis restaurer le TP ensuite.
                _cancel_all_open_futures_orders_fallback(client, symbol, preserve_tp_order=None, user_id=user_id)
                try:
                    sl_order = futures_place_conditional_order(
                        client, symbol, opposite, "STOP_MARKET", formatted_stop,
                    )
                    _restore_preserved_tp_order_if_needed(client, symbol, preserve_tp_order=tp_to_preserve)
                except Exception as retry_err:
                    _restore_preserved_tp_order_if_needed(client, symbol, preserve_tp_order=tp_to_preserve)
                    # Si un ordre protecteur closePosition existe déjà sur Binance, la position est protégée :
                    # retourner son orderId sans déclencher de faux safety_warn en boucle.
                    surviving = _find_futures_protective_orders(
                        client,
                        symbol,
                        side=opposite,
                        order_types={"STOP_MARKET", "STOP", "TAKE_PROFIT_MARKET", "TAKE_PROFIT"},
                        include_all_close_position=True,
                        user_id=user_id,
                    )
                    for surv in surviving:
                        if surv.get("orderId") is not None:
                            return str(surv["orderId"])
                    # Tenter de restaurer l'ancien SL
                    if old_stop_price_fallback:
                        try:
                            restored = futures_place_conditional_order(
                                client, symbol, opposite, "STOP_MARKET", old_stop_price_fallback,
                            )
                            if isinstance(restored, dict) and restored.get("orderId") is not None:
                                return str(restored["orderId"])
                        except Exception as rest_err:
                            rest_msg = getattr(rest_err, "message", str(rest_err))
                            if ("closePosition" in rest_msg or getattr(rest_err, "code", None) == -4130) and old_sl_order_id_fallback:
                                return str(old_sl_order_id_fallback)
                    retry_msg = getattr(retry_err, "message", str(retry_err))
                    if ("closePosition" in retry_msg or getattr(retry_err, "code", None) == -4130) and old_sl_order_id_fallback:
                        return str(old_sl_order_id_fallback)
                    raise BinanceClientError(
                        f"Erreur Binance (mise à jour SL {symbol}) : {retry_msg}"
                    )
        else:
            # Tenter de restaurer l'ancien SL si nous venons de l'annuler et que le nouveau prix est rejeté (ex: -2021 Order would immediately trigger)
            if ids_to_cancel and old_stop_price_fallback:
                try:
                    restored = futures_place_conditional_order(
                        client, symbol, opposite, "STOP_MARKET", old_stop_price_fallback,
                    )
                    if isinstance(restored, dict) and restored.get("orderId") is not None:
                        return str(restored["orderId"])
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


def check_api_key_permissions(api_key: str, api_secret: str, testnet: bool = True) -> dict:
    """
    Vérifie les permissions de la clé API Binance via get_api_key_permission / GET /sapi/v1/account/apiRestrictions.
    - Si enableWithdrawals=True -> lève BinanceClientError (refus strict avant stockage).
    - Si l'appel échoue (ex: endpoint non supporté sur Testnet) -> accepte avec avertissement.
    """
    perms = None
    last_err = None
    try:
        client = _build_resilient_client(api_key, api_secret, testnet=testnet)
        if hasattr(client, "get_api_key_permission"):
            res = client.get_api_key_permission()
            if isinstance(res, dict):
                perms = res
    except Exception as exc:
        last_err = exc

    if perms is None:
        try:
            res = _signed_rest_get(
                api_key,
                api_secret,
                "/sapi/v1/account/apiRestrictions",
                market_type="spot",
                testnet=testnet,
            )
            if isinstance(res, dict):
                perms = res
        except Exception as exc:
            last_err = exc

    if isinstance(perms, dict):
        if bool(perms.get("enableWithdrawals")):
            raise BinanceClientError(
                "Clé API refusée : la permission de retrait (enableWithdrawals=True) est activée. "
                "Veuillez désactiver les retraits sur cette clé Binance."
            )
        return {"checked": True, "warning": None, "permissions": perms}

    logger.warning(
        "Vérification des permissions API (/sapi/v1/account/apiRestrictions) indisponible (testnet=%s): %s",
        testnet,
        last_err,
    )
    return {
        "checked": False,
        "warning": "Vérification des restrictions de retrait indisponible (Testnet) ; clé acceptée avec avertissement.",
        "permissions": None,
    }


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
