"""
position_manager.py
---------------------
Suivi des positions ouvertes : PnL en temps réel, détection TP/SL atteints,
trailing stop dynamique basé sur l'ATR (Average True Range), rapprochement d'état
(reconciliation) périodique avec Binance, et fermeture (manuelle ou emergency stop).
"""

import time
from typing import Optional, Dict, Any, List, Tuple

try:
    from telegram.ext import ContextTypes
except ImportError:
    class ContextTypes:  # type: ignore
        DEFAULT_TYPE = Any

from config import ATR_MULTIPLIER_SL
from database import get_connection
from trading_config import get_config, TradingConfig, update_config, record_daily_pnl
from risk_manager import record_trade_loss, EPSILON
try:
    from indicators import atr as calc_atr
except Exception:
    calc_atr = None
from binance_manager import (
    get_price,
    close_position,
    cancel_order,
    get_open_binance_positions,
    get_open_binance_orders,
    get_klines_dataframe,
    replace_futures_stop_loss_order,
    BinanceClientError,
    ORDER_CONTEXT_AUTOTRADE,
    ORDER_CONTEXT_MANUAL_AUTHENTICATED,
    ORDER_CONTEXT_EMERGENCY,
)
try:
    from binance_manager import BinancePositionNotFound
except ImportError:  # modules de test qui stubent binance_manager sans cette exception
    class BinancePositionNotFound(BinanceClientError):  # type: ignore[no-redef]
        """Refus métier : aucune position Binance correspondante."""

from trading_logger import get_trading_logger, log_trade_closed, log_error
from trading_safety import engage_safe_mode, engage_safety_warn, clear_safety_warn, flush_safety_notifications
from utils import normalize_symbol

logger = get_trading_logger("position_manager")

# Multiplicateur ATR par défaut pour le Trailing Stop dynamique
DEFAULT_ATR_TRAILING_MULT: float = float(ATR_MULTIPLIER_SL or 1.5)


def reject_pending_trading_signals(user_id: int) -> int:
    """Rejette tous les signaux en attente pour un utilisateur donné."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE signals
                SET status = 'rejected'
                WHERE user_id = %s
                  AND status IN ('pending', 'active', 'awaiting_confirmation')
                """,
                (user_id,),
            )
            count = cur.rowcount
        conn.commit()
        return count
    finally:
        conn.close()


def get_open_trades(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Récupère les positions localement ouvertes en base de données."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if user_id:
                cur.execute(
                    "SELECT id, user_id, symbol, direction, entry_price, sl_price, tp_price, "
                    "quantity, leverage, market_type, sl_order_id, tp_order_id "
                    "FROM trades WHERE status = 'open' AND user_id = %s",
                    (user_id,),
                )
            else:
                cur.execute(
                    "SELECT id, user_id, symbol, direction, entry_price, sl_price, tp_price, "
                    "quantity, leverage, market_type, sl_order_id, tp_order_id "
                    "FROM trades WHERE status = 'open'"
                )
            cols = [
                "id", "user_id", "symbol", "direction", "entry_price", "sl_price",
                "tp_price", "quantity", "leverage", "market_type", "sl_order_id", "tp_order_id",
            ]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def _compute_pnl(
    direction: str,
    entry_price: float,
    current_price: float,
    quantity: float,
    leverage: int,
) -> Tuple[float, float]:
    """Calcule le PnL en USDT et en pourcentage avec protection contre la division par zéro."""
    if direction == "BUY":
        pnl_usdt = (current_price - entry_price) * quantity
    else:
        pnl_usdt = (entry_price - current_price) * quantity

    notional = (entry_price or 0.0) * (quantity or 0.0)
    if notional > EPSILON:
        pnl_pct = (pnl_usdt / notional) * 100.0 * max(int(leverage or 1), 1)
    else:
        pnl_pct = 0.0
    return pnl_usdt, pnl_pct


def _resolve_real_exit_price(trade: Dict[str, Any], fallback_price: float) -> float:
    """Récupère le prix d'exécution réel (ordre de clôture SL/TP ou userTrades Binance) quand disponible."""
    explicit_exec = trade.get("executed_exit_price") or trade.get("executed_price")
    if explicit_exec is not None:
        try:
            p = float(explicit_exec)
            if p > 0:
                return p
        except (TypeError, ValueError):
            pass

    user_id = trade.get("user_id")
    raw_sym = trade.get("symbol")
    if not user_id or not raw_sym:
        return float(fallback_price or 0.0)

    norm_sym = normalize_symbol(str(raw_sym))
    market_type = str(trade.get("market_type") or "futures").lower()
    direction = str(trade.get("direction") or "BUY").upper()
    opposite_side = "SELL" if direction == "BUY" else "BUY"

    try:
        from binance_manager import _client_for_user, _extract_order_fill_price

        client = _client_for_user(int(user_id), market_type=market_type)  # type: ignore[arg-type]
        for oid_field in ("sl_order_id", "tp_order_id", "close_order_id"):
            oid = trade.get(oid_field)
            if not oid:
                continue
            try:
                if market_type == "futures" and hasattr(client, "futures_get_order"):
                    ord_info = client.futures_get_order(symbol=norm_sym, orderId=oid)
                elif market_type != "futures" and hasattr(client, "get_order"):
                    ord_info = client.get_order(symbol=norm_sym, orderId=oid)
                else:
                    ord_info = None
                if isinstance(ord_info, dict):
                    st = str(ord_info.get("status") or "").upper()
                    if st in ("FILLED", "PARTIALLY_FILLED") or ("status" not in ord_info and (ord_info.get("avgPrice") or ord_info.get("price"))):
                        fill_p = _extract_order_fill_price(ord_info)
                        if fill_p and fill_p > 0:
                            return float(fill_p)
            except Exception:
                continue

        trades_list = None
        if market_type == "futures" and hasattr(client, "futures_account_trades"):
            trades_list = client.futures_account_trades(symbol=norm_sym, limit=10)
        elif market_type != "futures" and hasattr(client, "get_my_trades"):
            trades_list = client.get_my_trades(symbol=norm_sym, limit=10)

        if isinstance(trades_list, list) and trades_list:
            for tr in reversed(trades_list):
                if not isinstance(tr, dict):
                    continue
                side = str(tr.get("side") or "").upper()
                if not side and "buyer" in tr:
                    side = "BUY" if tr.get("buyer") else "SELL"
                if side and side != opposite_side:
                    continue
                try:
                    p = float(tr.get("price") or tr.get("avgPrice") or 0.0)
                    if p > 0:
                        return p
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass

    return float(fallback_price or 0.0)


def close_trade(trade: Dict[str, Any], exit_reason: str, current_price: float) -> Tuple[float, float]:
    """Clôture un trade localement en base de données et enregistre le PnL net journalier."""
    effective_exit_price = float(current_price or 0.0)
    if trade.get("executed_exit_price") or trade.get("executed_price") or trade.get("close_order_id"):
        effective_exit_price = _resolve_real_exit_price(trade, effective_exit_price)

    pnl_usdt, pnl_pct = _compute_pnl(
        trade["direction"],
        float(trade["entry_price"] or 0.0),
        effective_exit_price,
        float(trade["quantity"] or 0.0),
        int(trade.get("leverage") or 1),
    )

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE trades
                SET status = 'closed', closed_at = %s, exit_reason = %s,
                    pnl_usdt = %s, pnl_pct = %s
                WHERE id = %s AND status = 'open'
                """,
                (time.time(), exit_reason, pnl_usdt, pnl_pct, trade["id"]),
            )
            already_closed = getattr(cur, "rowcount", 1) == 0
        conn.commit()
    finally:
        conn.close()

    if already_closed:
        # Double fermeture évitée : le trade a déjà été clôturé (autre tâche / fermeture manuelle).
        # On ne ré-enregistre ni la perte ni le PnL journalier.
        return pnl_usdt, pnl_pct

    if pnl_usdt < 0:
        record_trade_loss(trade["user_id"], abs(pnl_usdt))
    elif pnl_usdt > 0:
        try:
            record_daily_pnl(trade["user_id"], pnl_usdt)
        except Exception:
            pass

    log_trade_closed(logger, trade["user_id"], trade["symbol"], exit_reason, pnl_usdt)
    return pnl_usdt, pnl_pct


def _fetch_latest_closed_atr(
    symbol: str,
    timeframe: str = "1h",
    market_type: str = "futures",
    period: int = 14,
) -> Optional[float]:
    """Récupère l'ATR calculé strictement sur la dernière bougie clôturée."""
    try:
        df = get_klines_dataframe(
            symbol=normalize_symbol(symbol),
            timeframe=timeframe or "1h",
            market_type=market_type,  # type: ignore[arg-type]
            limit=max(period * 4, 100),
        )
        if df is None or len(df) < period + 2:
            return None
        try:
            from signal_engine import SignalEngine
            if hasattr(SignalEngine, "filter_closed_candles"):
                closed_df = SignalEngine.filter_closed_candles(df)
            else:
                closed_df = df.iloc[:-1]
        except Exception:
            closed_df = df.iloc[:-1]
        if len(closed_df) < period + 1:
            return None
        atr_series = calc_atr(closed_df["High"], closed_df["Low"], closed_df["Close"], period=period)
        val = float(atr_series.iloc[-1])
        if val > EPSILON and not (val != val):  # check not NaN
            return val
    except Exception as e:
        logger.debug("Impossible de récupérer l'ATR dynamique pour %s: %s", symbol, e)
    return None


def update_trailing_stop(
    trade: Dict[str, Any],
    config: TradingConfig,
    current_price: float,
    atr_value: Optional[float] = None,
) -> Optional[float]:
    """Calcule le nouveau Stop Loss dynamique basé sur l'ATR (Average True Range).

    Remplace les pourcentages statiques par une distance dynamique `ATR * multiplicateur`.
    Si l'ATR n'est pas fourni en argument, il est récupéré sur la dernière bougie clôturée.
    En dernier recours (indisponibilité réseau Klines), utilise `trailing_stop_pct` comme repli sûr.
    """
    if not config.trailing_stop or current_price <= EPSILON:
        return None

    if atr_value is None or atr_value <= EPSILON:
        atr_value = _fetch_latest_closed_atr(
            symbol=trade["symbol"],
            timeframe=getattr(config, "analysis_timeframe", "1h"),
            market_type=trade.get("market_type", "futures"),
        )

    # Multiplicateur dynamique (utilise trailing_stop_pct comme facteur d'échelle s'il est configuré, sinon ATR_MULTIPLIER_SL)
    atr_mult = float(config.trailing_stop_pct) if config.trailing_stop_pct and config.trailing_stop_pct >= 0.5 else DEFAULT_ATR_TRAILING_MULT

    if atr_value is not None and atr_value > EPSILON:
        trail_distance = atr_value * atr_mult
    else:
        # Fallback de sécurité si les klines ne sont pas joignables
        trail_pct = max(float(config.trailing_stop_pct or 1.0), 0.05) / 100.0
        trail_distance = current_price * trail_pct

    # Garantie d'une distance minimale non nulle
    min_dist = max(current_price * 0.0005, EPSILON)
    trail_distance = max(trail_distance, min_dist)

    current_sl = float(trade["sl_price"]) if trade.get("sl_price") is not None else None
    tp_price = float(trade["tp_price"]) if trade.get("tp_price") is not None else None
    direction = (trade.get("direction") or "BUY").upper()
    symbol = normalize_symbol(str(trade.get("symbol") or ""))
    # Pas minimum de déplacement pour éviter de remplacer un SL identique au tick près toutes les 10s
    min_step = 1.0 if symbol.startswith("BTC") else max(current_price * 0.0005, EPSILON)
    # Tampon de sécurité par rapport au prix courant pour éviter que le prix du marché ne franchisse
    # new_sl pendant l'appel réseau (ce qui transformerait le STOP_MARKET en GTE et déclencherait -4130 face au TP)
    safety_buffer = max(current_price * 0.001, min_step)

    if direction == "BUY":
        new_sl = min(current_price - trail_distance, current_price - safety_buffer)
        if tp_price is not None and new_sl >= tp_price - safety_buffer:
            return None
        if new_sl > EPSILON and (current_sl is None or new_sl >= current_sl + min_step):
            return new_sl
    else:
        new_sl = max(current_price + trail_distance, current_price + safety_buffer)
        if tp_price is not None and new_sl <= tp_price + safety_buffer:
            return None
        if current_sl is None or new_sl <= current_sl - min_step:
            return new_sl
    return None


def _persist_new_sl(trade_id: int, new_sl: float, sl_order_id: Optional[str] = None) -> None:
    """Met à jour le Stop Loss (et optionnellement l'ID d'ordre SL) en base de données."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if sl_order_id is not None:
                cur.execute(
                    "UPDATE trades SET sl_price = %s, sl_order_id = %s WHERE id = %s",
                    (new_sl, str(sl_order_id), trade_id),
                )
            else:
                cur.execute(
                    "UPDATE trades SET sl_price = %s WHERE id = %s",
                    (new_sl, trade_id),
                )
        conn.commit()
    finally:
        conn.close()


# Durée (s) pendant laquelle on laisse un ordre SL/TP Binance encore actif se déclencher seul
# avant de forcer une fermeture de sécurité (prix déjà au-delà du niveau).
PROTECTIVE_ORDER_GRACE_SECONDS = 45
_breach_since: Dict[int, float] = {}
_closing_trades: set = set()


def _protective_order_alive(user_id: int, symbol: str, order_id: Any) -> bool:
    """Vrai si l'ordre de protection enregistré existe réellement parmi les ordres ouverts Binance.
    Lève BinanceClientError (erreur réseau/API réelle) si la vérification est impossible."""
    if not order_id:
        return False
    open_orders = get_open_binance_orders(user_id, market_type="futures", symbol=normalize_symbol(symbol))
    return any(str(o.get("orderId")) == str(order_id) for o in open_orders if isinstance(o, dict))


def _is_business_refusal(err: Exception) -> bool:
    """Refus métier (position absente / fermeture refusée) par opposition à une erreur réseau/API."""
    return isinstance(err, BinancePositionNotFound) or "Fermeture refusée" in str(err)


def _remote_position_exists(user_id: int, symbol: str, direction: str) -> bool:
    """Vérifie si une position est toujours ouverte sur Binance Futures."""
    norm_sym = normalize_symbol(symbol)
    positions = get_open_binance_positions(user_id, market_type="futures")
    return any(normalize_symbol(p["symbol"]) == norm_sym and p["direction"] == direction for p in positions)


def _cancel_remaining_protection(trade: Dict[str, Any], executed_reason: str) -> None:
    """Annule les ordres protecteurs SL/TP restants à la clôture (Futures et Spot OCO)."""
    reason_up = str(executed_reason or "").upper()
    if reason_up == "TP":
        oids = [trade.get("sl_order_id")]
    elif reason_up == "SL":
        oids = [trade.get("tp_order_id")]
    else:
        oids = [trade.get("sl_order_id"), trade.get("tp_order_id")]
    seen: set[str] = set()
    for oid in oids:
        if oid and str(oid) not in seen:
            seen.add(str(oid))
            cancel_order(
                trade["user_id"],
                normalize_symbol(trade["symbol"]),
                str(oid),
                trade["market_type"],
                execution_context=ORDER_CONTEXT_AUTOTRADE,
            )


def _trade_key(trade: Dict[str, Any]) -> Tuple[str, str]:
    """Génère une clé canonique (symbole normalisé, direction) pour le rapprochement."""
    return (normalize_symbol(trade["symbol"]), str(trade["direction"]).upper())


def reconcile_user_positions(user_id: int, startup_mode: bool = False, context=None) -> Dict[str, Any]:
    """Synchronise les positions locales en base avec l'état réel renvoyé par l'API Binance.

    Purge automatiquement :
    - Les positions locales orphelines (fermées manuellement sur Binance ou liquidées).
    - Les ordres protecteurs (SL/TP) orphelins sur Binance qui ne correspondent plus à aucune position ouverte.
    Distingue :
    - Erreurs réseau / ordres protecteurs manquants -> safety_warn (temporaire, auto-clear).
    - Position Binance sans trade local (hors startup) -> safety_lock (critique).
    """
    local_trades = [t for t in get_open_trades(user_id) if t["market_type"] == "futures"]
    local_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    duplicate_local_trades: List[Dict[str, Any]] = []

    for t in local_trades:
        key = _trade_key(t)
        if key in local_by_key:
            duplicate_local_trades.append(t)
        else:
            local_by_key[key] = t

    try:
        remote_positions = get_open_binance_positions(user_id, market_type="futures")
    except BinanceClientError as e:
        log_error(logger, user_id, "reconcile.positions", str(e))
        engage_safety_warn(user_id, f"Erreur réseau/API Binance sur positions: {e}", context=context)
        return {
            "user_id": user_id,
            "local_open": len(local_trades),
            "remote_open": 0,
            "missing_remote": [],
            "missing_local": [],
            "repaired": 0,
            "warn": str(e),
        }

    remote_by_key = {(normalize_symbol(p["symbol"]), str(p["direction"]).upper()): p for p in remote_positions}

    repaired = 0
    missing_remote: List[Tuple[str, str]] = []
    missing_local: List[Tuple[str, str]] = []
    had_warning = False

    # 1. Purge des doublons locaux éventuels sans position correspondante
    for dup_trade in duplicate_local_trades:
        key = _trade_key(dup_trade)
        if key not in remote_by_key:
            try:
                current_price = get_price(user_id, dup_trade["symbol"], dup_trade["market_type"])
                close_trade(dup_trade, "reconciled_duplicate_orphan", current_price)
                repaired += 1
            except Exception as e:
                log_error(logger, user_id, "reconcile.close_dup", str(e))

    # 2. Purge des positions locales qui n'existent plus sur Binance (fermées manuellement / liquidées / SL-TP)
    for key, trade in local_by_key.items():
        if key in remote_by_key:
            continue
        missing_remote.append(key)
        try:
            fallback_price = float(trade.get("entry_price") or 0.0)
            try:
                fallback_price = get_price(user_id, trade["symbol"], trade["market_type"])
            except Exception:
                pass
            fill_price = _resolve_real_exit_price(trade, fallback_price)
            # Annulation préventive des ordres SL/TP restants pour ce trade orphelin
            for oid in (trade.get("sl_order_id"), trade.get("tp_order_id")):
                if oid:
                    cancel_order(
                        user_id,
                        trade["symbol"],
                        oid,
                        trade["market_type"],
                        execution_context=ORDER_CONTEXT_AUTOTRADE,
                    )
            close_trade(trade, "reconciled_missing_remote", fill_price)
            repaired += 1
        except Exception as e:
            log_error(logger, user_id, "reconcile.close_local", str(e))

    # 3. Détection des positions ouvertes sur Binance mais absentes de la base locale
    for key in remote_by_key:
        if key not in local_by_key:
            missing_local.append(key)

    if missing_local:
        log_error(
            logger,
            user_id,
            "reconcile.missing_local",
            f"Positions Binance sans trade local: {missing_local}",
        )
        if startup_mode:
            logger.warning(
                "reconcile startup_mode user=%s: ignoring %d orphaned Binance position(s) %s",
                user_id,
                len(missing_local),
                missing_local,
            )
        else:
            engage_safe_mode(
                user_id,
                f"Divergence critique: position(s) Binance sans trade local {missing_local}",
                context=context,
            )

    # 4. Vérification des ordres protecteurs sur les positions actives
    try:
        open_orders = get_open_binance_orders(user_id, market_type="futures")
        open_order_ids = {str(order.get("orderId")) for order in open_orders if order.get("orderId") is not None}
        for trade in local_trades:
            if _trade_key(trade) not in remote_by_key:
                continue
            # Si un ordre LIMIT Futures vient d'être rempli (position présente dans remote_by_key) sans SL/TP posés, les poser maintenant
            need_sl = bool(trade.get("sl_price") and not trade.get("sl_order_id"))
            need_tp = bool(trade.get("tp_price") and not trade.get("tp_order_id"))
            if need_sl or need_tp:
                try:
                    from binance_manager import _client_for_user, get_symbol_filters, _place_futures_protective_orders
                    client = _client_for_user(user_id, market_type="futures")
                    norm_s = normalize_symbol(trade["symbol"])
                    opposite = "SELL" if str(trade["direction"]).upper() == "BUY" else "BUY"
                    filters = get_symbol_filters(client, norm_s, "futures")
                    sl_oid, tp_oid = _place_futures_protective_orders(
                        client,
                        norm_s,
                        opposite,
                        float(trade["sl_price"]) if need_sl else None,
                        float(trade["tp_price"]) if need_tp else None,
                        filters,
                    )
                    if sl_oid or tp_oid:
                        conn = get_connection()
                        try:
                            with conn.cursor() as cur:
                                cur.execute(
                                    "UPDATE trades SET sl_order_id = COALESCE(%s, sl_order_id), tp_order_id = COALESCE(%s, tp_order_id) WHERE id = %s",
                                    (sl_oid, tp_oid, trade["id"]),
                                )
                            conn.commit()
                        finally:
                            conn.close()
                        if sl_oid:
                            trade["sl_order_id"] = sl_oid
                            open_order_ids.add(str(sl_oid))
                        if tp_oid:
                            trade["tp_order_id"] = tp_oid
                            open_order_ids.add(str(tp_oid))
                except Exception as place_err:
                    log_error(logger, user_id, "reconcile.place_protection", str(place_err))
            for field in ("sl_order_id", "tp_order_id"):
                oid = trade.get(field)
                if oid and str(oid) not in open_order_ids:
                    had_warning = True
                    msg_warn = f"Ordre protecteur ({field}) absent côté Binance pour trade #{trade['id']} ({trade['symbol']})"
                    log_error(logger, user_id, f"reconcile.{field}", msg_warn)
                    engage_safety_warn(user_id, msg_warn, context=context)
    except BinanceClientError as e:
        had_warning = True
        log_error(logger, user_id, "reconcile.orders", str(e))
        engage_safety_warn(user_id, f"Erreur réseau/API lecture ordres protecteurs: {e}", context=context)

    if not missing_local and not had_warning:
        cfg = get_config(user_id)
        if cfg.safety_warn:
            clear_safety_warn(user_id)

    return {
        "user_id": user_id,
        "local_open": len(local_trades),
        "remote_open": len(remote_positions),
        "missing_remote": missing_remote,
        "missing_local": missing_local,
        "repaired": repaired,
    }


def _active_trading_user_ids() -> List[int]:
    """Récupère la liste des utilisateurs ayant des clés API Binance valides."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT c.user_id
                FROM binance_credentials c
                LEFT JOIN trading_config t ON t.user_id = c.user_id
                WHERE c.is_valid = TRUE
                  AND COALESCE(t.market_type, 'futures') = 'futures'
                """
            )
            return [int(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()


def reconcile_all_accounts(context=None, startup_mode: bool = False) -> List[Dict[str, Any]]:
    """Exécute le rapprochement d'état (reconciliation) pour tous les comptes actifs."""
    reports: List[Dict[str, Any]] = []
    for user_id in _active_trading_user_ids():
        try:
            reports.append(reconcile_user_positions(user_id, startup_mode=startup_mode, context=context))
        except BinanceClientError as e:
            log_error(logger, user_id, "reconcile_all", str(e))
            engage_safety_warn(user_id, f"Erreur réseau Binance lors de la réconciliation: {e}", context=context)
        except Exception as e:
            log_error(logger, user_id, "reconcile_all_unexpected", str(e))
    return reports


async def monitor_open_positions(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job APScheduler : appelé toutes les 10-20s pour surveiller les positions réelles Binance."""
    await flush_safety_notifications(context)
    for trade in get_open_trades():
        try:
            config = get_config(trade["user_id"])
            current_price = get_price(trade["user_id"], trade["symbol"], trade["market_type"])

            # Vérification d'absence d'ordre protecteur (uniquement safety_warn, jamais safety_lock)
            if trade["market_type"] == "futures" and (not trade.get("sl_order_id") or not trade.get("tp_order_id")):
                engage_safety_warn(
                    trade["user_id"],
                    f"Ordre protecteur SL/TP manquant temporairement sur position #{trade['id']} ({trade['symbol']})",
                    context=context,
                )

            hit_tp = bool(
                trade["tp_price"]
                and (
                    (trade["direction"] == "BUY" and current_price >= trade["tp_price"])
                    or (trade["direction"] == "SELL" and current_price <= trade["tp_price"])
                )
            )
            hit_sl = bool(
                trade["sl_price"]
                and (
                    (trade["direction"] == "BUY" and current_price <= trade["sl_price"])
                    or (trade["direction"] == "SELL" and current_price >= trade["sl_price"])
                )
            )

            if not (hit_tp or hit_sl):
                _breach_since.pop(trade["id"], None)

            if hit_tp or hit_sl:
                reason = "TP" if hit_tp else "SL"
                protective_order_id = trade.get("tp_order_id") if hit_tp else trade.get("sl_order_id")
                exit_price = current_price
                safety_close = False
                if trade["id"] in _closing_trades:
                    continue  # fermeture déjà en cours pour ce trade : pas de double ordre
                if trade["market_type"] == "spot":
                    # En Spot, si un ordre OCO (sl_order_id / tp_order_id) existe, on l'annule d'abord pour libérer le solde si non encore exécuté
                    _cancel_remaining_protection(trade, "MANUAL")
                    if not protective_order_id:
                        close_res = close_position(
                            trade["user_id"],
                            trade["symbol"],
                            trade["direction"],
                            trade["quantity"],
                            trade["market_type"],
                            execution_context=ORDER_CONTEXT_AUTOTRADE,
                        )
                        if isinstance(close_res, dict) and close_res.get("executed_price"):
                            exit_price = float(close_res["executed_price"])
                    else:
                        try:
                            close_res = close_position(
                                trade["user_id"],
                                trade["symbol"],
                                trade["direction"],
                                trade["quantity"],
                                trade["market_type"],
                                execution_context=ORDER_CONTEXT_AUTOTRADE,
                            )
                            if isinstance(close_res, dict) and close_res.get("executed_price"):
                                exit_price = float(close_res["executed_price"])
                        except Exception:
                            # L'ordre OCO côté exchange a déjà vendu la position Spot
                            pass
                else:
                    # Futures : le niveau SL/TP est franchi. L'ordre de protection enregistré n'est cru que s'il
                    # existe réellement sur Binance ; sinon (ou s'il ne se déclenche pas), fermeture de sécurité.
                    if not protective_order_id:
                        safety_close = True
                    elif not _protective_order_alive(trade["user_id"], trade["symbol"], protective_order_id):
                        safety_close = True
                        logger.warning(
                            "Ordre protecteur %s introuvable côté Binance pour trade #%s (%s) alors que %s est franchi : fermeture de sécurité.",
                            protective_order_id, trade["id"], trade["symbol"], reason,
                        )
                    elif _remote_position_exists(trade["user_id"], trade["symbol"], trade["direction"]):
                        # Ordre actif et position encore ouverte : on laisse Binance exécuter, avec un délai de grâce.
                        first_seen = _breach_since.setdefault(trade["id"], time.time())
                        if time.time() - first_seen < PROTECTIVE_ORDER_GRACE_SECONDS:
                            continue
                        safety_close = True
                        logger.warning(
                            "Ordre protecteur %s actif mais non déclenché depuis %ss (trade #%s %s) : fermeture de sécurité.",
                            protective_order_id, PROTECTIVE_ORDER_GRACE_SECONDS, trade["id"], trade["symbol"],
                        )
                    if safety_close:
                        _closing_trades.add(trade["id"])
                        try:
                            close_res = close_position(
                                trade["user_id"],
                                trade["symbol"],
                                trade["direction"],
                                trade["quantity"],
                                trade["market_type"],
                                execution_context=ORDER_CONTEXT_AUTOTRADE,
                            )
                            if isinstance(close_res, dict) and close_res.get("executed_price"):
                                exit_price = float(close_res["executed_price"])
                        except BinancePositionNotFound:
                            # Aucune position réelle sur Binance : ce n'est pas une panne réseau,
                            # on synchronise l'état local (prix réel de sortie si retrouvable).
                            exit_price = _resolve_real_exit_price(trade, current_price)
                            logger.info(
                                "Trade #%s %s: aucune position Binance, synchronisation locale (%s).",
                                trade["id"], trade["symbol"], reason,
                            )
                        finally:
                            _closing_trades.discard(trade["id"])
                _breach_since.pop(trade["id"], None)
                if trade["market_type"] != "spot":
                    # Fermeture de sécurité : on annule SL ET TP restants (aucun ordre orphelin).
                    _cancel_remaining_protection(trade, "SAFETY" if safety_close else reason)
                pnl_usdt, pnl_pct = close_trade(trade, reason, exit_price)
                if context and hasattr(context, "bot"):
                    await context.bot.send_message(
                        chat_id=trade["user_id"],
                        text=(
                            f"{'🟢' if pnl_usdt >= 0 else '🔴'} *Position fermée ({reason})*\n"
                            f"Symbole : `{trade['symbol']}`\n"
                            f"PnL : {pnl_usdt:.2f} USDT ({pnl_pct:.2f}%)"
                        ),
                        parse_mode="Markdown",
                    )
                continue

            new_sl = update_trailing_stop(trade, config, current_price)
            if new_sl:
                if trade["market_type"] == "spot":
                    _persist_new_sl(trade["id"], new_sl)
                    trade["sl_price"] = new_sl
                else:
                    try:
                        new_sl_oid = replace_futures_stop_loss_order(
                            user_id=trade["user_id"],
                            symbol=trade["symbol"],
                            direction=trade["direction"],
                            new_sl_price=new_sl,
                            old_sl_order_id=trade.get("sl_order_id"),
                            execution_context=ORDER_CONTEXT_AUTOTRADE,
                        )
                        if not new_sl_oid:
                            raise BinanceClientError(
                                f"Nouveau SL non confirmé pour {trade['symbol']} (aucun orderId retourné)"
                            )
                        _persist_new_sl(trade["id"], new_sl, sl_order_id=new_sl_oid)
                        trade["sl_price"] = new_sl
                        trade["sl_order_id"] = str(new_sl_oid)
                    except Exception as sl_err:
                        err_str = str(sl_err)
                        if "closePosition in the direction is existing" in err_str or "-4130" in err_str:
                            # Un ordre protecteur closePosition existe déjà sur Binance : la position est protégée
                            logger.info(
                                "Ordre protecteur closePosition déjà actif sur Binance pour %s (user=%s) — aucun safety_warn requis.",
                                trade["symbol"],
                                trade["user_id"],
                            )
                            if config.safety_warn:
                                clear_safety_warn(trade["user_id"])
                            continue
                        log_error(
                            logger,
                            trade["user_id"],
                            "trailing_stop",
                            f"Échec mise à jour SL dynamique Futures: {sl_err}",
                        )
                        engage_safety_warn(
                            trade["user_id"],
                            f"Échec temporaire déplacement SL Futures ({trade['symbol']}): {sl_err}",
                            context=context,
                        )
                        continue

            if config.safety_warn and (trade["market_type"] != "futures" or (trade.get("sl_order_id") and trade.get("tp_order_id"))):
                clear_safety_warn(trade["user_id"])

        except BinanceClientError as e:
            log_error(logger, trade["user_id"], "monitor_open_positions", str(e))
            if _is_business_refusal(e):
                engage_safety_warn(trade["user_id"], f"Refus métier pendant surveillance position (pas une erreur réseau): {e}", context=context)
            else:
                engage_safety_warn(trade["user_id"], f"Erreur réseau/API pendant surveillance position: {e}", context=context)
        except Exception as e:
            log_error(logger, trade["user_id"], "monitor_open_positions_unexpected", str(e))


def close_trade_manual(trade_id: int, user_id: int) -> Dict[str, Any]:
    """Ferme manuellement une position ouverte et synchronise immédiatement avec Binance."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, symbol, direction, entry_price, sl_price, tp_price, "
                "quantity, leverage, market_type, sl_order_id, tp_order_id "
                "FROM trades WHERE id = %s AND user_id = %s AND status = 'open'",
                (trade_id, user_id),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise ValueError("Position introuvable ou déjà fermée.")

    cols = [
        "id", "user_id", "symbol", "direction", "entry_price", "sl_price",
        "tp_price", "quantity", "leverage", "market_type", "sl_order_id", "tp_order_id",
    ]
    trade = dict(zip(cols, row))
    norm_sym = normalize_symbol(trade["symbol"])
    current_price = float(trade["entry_price"] or 0.0)
    try:
        current_price = get_price(user_id, norm_sym, trade["market_type"])
    except Exception:
        pass

    if trade["market_type"] == "futures":
        remote_positions = get_open_binance_positions(user_id, market_type="futures")
        remote = next(
            (
                p for p in remote_positions
                if normalize_symbol(p["symbol"]) == norm_sym
                and p["direction"] == trade["direction"]
            ),
            None,
        )
        if not remote:
            # La position a déjà été clôturée sur Binance (TP/SL déclenché, liquidation ou fermeture depuis l'app Binance).
            # On annule les ordres protecteurs résiduels et on clôture proprement la ligne locale sans lever d'erreur bloquante.
            for oid in (trade.get("sl_order_id"), trade.get("tp_order_id")):
                if oid:
                    try:
                        cancel_order(
                            user_id,
                            norm_sym,
                            oid,
                            trade["market_type"],
                            execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED,
                        )
                    except Exception:
                        pass
            pnl_usdt, pnl_pct = close_trade(trade, "manual_synced", current_price)
            return {
                "pnl_usdt": pnl_usdt,
                "pnl_pct": pnl_pct,
                "symbol": norm_sym,
                "already_closed_on_binance": True,
            }

        # Si la taille sur Binance diffère (ex: fermeture partielle sur Binance), on ferme la taille réelle sur Binance
        qty_to_close = float(remote["quantity"])
        trade["quantity"] = qty_to_close
    else:
        qty_to_close = float(trade["quantity"])

    close_res = close_position(
        user_id,
        norm_sym,
        trade["direction"],
        qty_to_close,
        trade["market_type"],
        execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED,
    )
    exit_price = (
        float(close_res["executed_price"])
        if isinstance(close_res, dict) and close_res.get("executed_price")
        else current_price
    )

    for oid in (trade.get("sl_order_id"), trade.get("tp_order_id")):
        if oid:
            cancel_order(
                user_id,
                norm_sym,
                oid,
                trade["market_type"],
                execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED,
            )

    pnl_usdt, pnl_pct = close_trade(trade, "manual", exit_price)
    return {"pnl_usdt": pnl_usdt, "pnl_pct": pnl_pct, "symbol": norm_sym}


def close_binance_position_direct(
    user_id: int,
    symbol: str,
    direction: Optional[str] = None,
    market_type: str = "futures",
) -> Dict[str, Any]:
    """Ferme directement une position ouverte sur Binance par son symbole (même si aucun trade_id local ne correspond)."""
    norm_sym = normalize_symbol(symbol)
    local_trades = [
        t for t in get_open_trades(user_id)
        if normalize_symbol(t["symbol"]) == norm_sym
        and (not direction or t["direction"].upper() == direction.upper())
    ]

    if market_type == "futures":
        remote_positions = get_open_binance_positions(user_id, market_type="futures")
        remote = next(
            (
                p for p in remote_positions
                if normalize_symbol(p["symbol"]) == norm_sym
                and (not direction or p["direction"].upper() == direction.upper())
            ),
            None,
        )
        if not remote:
            # Si aucune position n'est ouverte sur Binance mais qu'un trade local est resté ouvert, on le clôture
            if local_trades:
                return close_trade_manual(int(local_trades[0]["id"]), user_id)
            raise ValueError(f"Aucune position ouverte trouvée sur Binance pour {norm_sym}.")

        eff_dir = str(remote["direction"]).upper()
        eff_qty = float(remote["quantity"])
        entry_p = float(remote.get("entry_price") or 0.0)
        lev = int(remote.get("leverage") or 1)
        mark_p = float(remote.get("mark_price") or entry_p or 0.0)
        try:
            current_price = get_price(user_id, norm_sym, "futures")
        except Exception:
            current_price = mark_p

        close_res = close_position(
            user_id,
            norm_sym,
            eff_dir,
            eff_qty,
            "futures",
            execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED,
        )
        exit_price = (
            float(close_res["executed_price"])
            if isinstance(close_res, dict) and close_res.get("executed_price")
            else current_price
        )

        # Annuler tous les ordres protecteurs ouverts sur ce symbole
        try:
            for o in get_open_binance_orders(user_id, market_type="futures", symbol=norm_sym):
                if o.get("orderId"):
                    cancel_order(
                        user_id,
                        norm_sym,
                        str(o["orderId"]),
                        "futures",
                        execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED,
                    )
        except Exception:
            pass

        if local_trades:
            for lt in local_trades:
                lt["quantity"] = eff_qty
                pnl_usdt, pnl_pct = close_trade(lt, "manual", exit_price)
            return {"pnl_usdt": pnl_usdt, "pnl_pct": pnl_pct, "symbol": norm_sym}

        pnl_usdt, pnl_pct = _compute_pnl(eff_dir, entry_p, exit_price, eff_qty, lev)
        return {"pnl_usdt": pnl_usdt, "pnl_pct": pnl_pct, "symbol": norm_sym}

    if local_trades:
        return close_trade_manual(int(local_trades[0]["id"]), user_id)
    raise ValueError(f"Aucune position ouverte trouvée pour {norm_sym}.")


def emergency_stop_all(user_id: int) -> int:
    """Ferme en urgence toutes les positions ouvertes localement et réellement sur Binance."""
    closed = 0
    local_trades = get_open_trades(user_id)
    local_keys = {_trade_key(t): t for t in local_trades}

    for trade in local_trades:
        try:
            norm_sym = normalize_symbol(trade["symbol"])
            current_price = get_price(user_id, norm_sym, trade["market_type"])
            close_res = close_position(
                user_id,
                norm_sym,
                trade["direction"],
                trade["quantity"],
                trade["market_type"],
                execution_context=ORDER_CONTEXT_EMERGENCY,
            )
            exit_price = (
                float(close_res["executed_price"])
                if isinstance(close_res, dict) and close_res.get("executed_price")
                else current_price
            )
            for oid in (trade.get("sl_order_id"), trade.get("tp_order_id")):
                if oid:
                    cancel_order(
                        user_id,
                        norm_sym,
                        oid,
                        trade["market_type"],
                        execution_context=ORDER_CONTEXT_EMERGENCY,
                    )
            close_trade(trade, "emergency", exit_price)
            closed += 1
        except Exception as e:
            log_error(logger, user_id, "emergency_stop_all.local", str(e))

    try:
        for pos in get_open_binance_positions(user_id, market_type="futures"):
            norm_sym = normalize_symbol(pos["symbol"])
            key = (norm_sym, pos["direction"])
            if key in local_keys:
                continue
            close_position(
                user_id,
                norm_sym,
                pos["direction"],
                pos["quantity"],
                "futures",
                execution_context=ORDER_CONTEXT_EMERGENCY,
            )
            for order in get_open_binance_orders(user_id, market_type="futures", symbol=norm_sym):
                cancel_order(
                    user_id,
                    norm_sym,
                    order.get("orderId"),
                    "futures",
                    execution_context=ORDER_CONTEXT_EMERGENCY,
                )
            closed += 1
    except Exception as e:
        log_error(logger, user_id, "emergency_stop_all.remote", str(e))

    reject_pending_trading_signals(user_id)
    update_config(user_id, auto_trade=False, periodic_analysis_enabled=False)
    return closed
