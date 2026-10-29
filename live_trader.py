"""
live_trader.py
----------------
Module indépendant pour le Live Trading manuel depuis Telegram.
Les ordres réels ne sont envoyés qu'après validation et confirmation explicite.
"""

from __future__ import annotations

import json
import math
import time
import hashlib
import uuid
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Optional

from binance.exceptions import BinanceAPIException, BinanceOrderException

from binance_manager import (
    BinanceClientError,
    _client_for_user,
    _extract_order_fill_price,
    _lookup_order_by_client_id,
    _place_futures_protective_orders,
    _place_spot_oco_order,
    futures_cancel_conditional_order,
    futures_list_conditional_orders,
    get_mark_price,
    rebase_protective_levels,
    get_account_balance,
    get_available_balance,
    get_full_account_info,
    get_open_binance_positions,
    get_price,
    get_symbol_filters,
    make_client_order_id,
    round_step_size,
    set_leverage,
    _assert_order_context_allowed,
)
from config import DOCUMENTED_SYMBOLS
from database import get_connection
import security_manager
from trading_config import get_config
from risk_manager import check_can_open_position, check_symbol_allowed, compute_risk_based_quantity
from trading_logger import get_trading_logger
from trading_safety import SafetyError, assert_trading_allowed, engage_safe_mode, user_trading_lock
from utils import normalize_symbol

logger = get_trading_logger("live_trader")

_IDEMPOTENCY_MEMORY_STORE: dict[tuple[int, str], dict] = {}


@dataclass
class LiveOrderDraft:
    symbol: str
    side: str
    amount: float
    amount_mode: str = "fixed"
    leverage: int = 1
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    trailing_stop: bool = False
    order_type: str = "MARKET"
    entry_price: Optional[float] = None
    margin_type: str = "ISOLATED"
    reduce_only: bool = False
    market_type: str = "futures"


def _filter_float(filters: dict, filter_type: str, key: str, default: float = 0.0) -> float:
    try:
        return float(filters.get(filter_type, {}).get(key, default))
    except (TypeError, ValueError):
        return default


def _get_max_leverage(client, symbol: str) -> Optional[int]:
    try:
        brackets = client.futures_leverage_bracket(symbol=symbol)
        if brackets and isinstance(brackets, list) and brackets[0].get("brackets"):
            return int(brackets[0]["brackets"][0].get("initialLeverage", 125))
    except Exception as e:
        logger.debug("Leverage bracket unavailable for %s: %s", symbol, e)
    return None


def _round_tick(value: Optional[float], tick_size: float) -> Optional[float]:
    """Arrondit au tick le plus proche avec Decimal (pas de dérive flottante ni de tick « perdu »)."""
    if value is None or not tick_size or tick_size <= 0:
        return value
    tick = Decimal(str(tick_size))
    snapped = (Decimal(str(value)) / tick).to_integral_value(rounding=ROUND_HALF_UP) * tick
    return float(snapped)


def _get_idempotent_result(user_id: int, key: str) -> Optional[dict]:
    if not key:
        return None
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS order_idempotency (
                    user_id BIGINT NOT NULL,
                    key TEXT NOT NULL,
                    result_json TEXT,
                    created_at DOUBLE PRECISION NOT NULL,
                    UNIQUE(user_id, key)
                )
                """
            )
            cur.execute(
                "SELECT result_json FROM order_idempotency WHERE user_id = %s AND key = %s",
                (user_id, key),
            )
            row = cur.fetchone()
            if row is not None:
                raw_json = row[0] if not isinstance(row, dict) else row.get("result_json")
                if isinstance(raw_json, str) and raw_json:
                    return json.loads(raw_json)
    except Exception as e:
        logger.debug("Idempotency DB lookup fallback for user=%s key=%s: %s", user_id, key, e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    return _IDEMPOTENCY_MEMORY_STORE.get((int(user_id), str(key)))


def _save_idempotent_result(user_id: int, key: str, result: dict) -> None:
    if not key:
        return
    serialized = json.dumps(result, default=str)
    _IDEMPOTENCY_MEMORY_STORE[(int(user_id), str(key))] = json.loads(serialized)
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS order_idempotency (
                    user_id BIGINT NOT NULL,
                    key TEXT NOT NULL,
                    result_json TEXT,
                    created_at DOUBLE PRECISION NOT NULL,
                    UNIQUE(user_id, key)
                )
                """
            )
            cur.execute(
                """
                INSERT INTO order_idempotency (user_id, key, result_json, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, key) DO UPDATE
                SET result_json = EXCLUDED.result_json
                """,
                (user_id, key, serialized, time.time()),
            )
        conn.commit()
    except Exception as e:
        logger.debug("Idempotency DB save fallback for user=%s key=%s: %s", user_id, key, e)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def build_draft(
    user_id: int,
    symbol: str,
    side: str,
    amount: float,
    leverage: Optional[int] = None,
    sl_price: Optional[float] = None,
    tp_price: Optional[float] = None,
    amount_mode: str = "fixed",
    order_type: str = "MARKET",
    entry_price: Optional[float] = None,
    margin_type: str = "ISOLATED",
    reduce_only: bool = False,
    trailing_stop: bool = False,
) -> LiveOrderDraft:
    config = get_config(user_id)
    side = side.upper()
    if side not in ("BUY", "SELL"):
        raise ValueError("Le sens doit être BUY ou SELL.")
    amount_mode = amount_mode.lower()
    if amount_mode not in ("fixed", "percentage", "risk"):
        raise ValueError("Le mode montant doit être fixed, percentage ou risk.")
    order_type = order_type.upper()
    if order_type not in ("MARKET", "LIMIT"):
        raise ValueError("Le type d'ordre doit être MARKET ou LIMIT.")
    margin_type = margin_type.upper()
    if margin_type not in ("CROSS", "ISOLATED"):
        raise ValueError("Le mode marge doit être CROSS ou ISOLATED.")
    if order_type == "LIMIT" and not entry_price:
        raise ValueError("Un prix d'entrée est requis pour un ordre LIMIT.")

    eff_leverage = 1 if config.market_type == "spot" and leverage is None else int(leverage if leverage is not None else config.leverage)

    return LiveOrderDraft(
        symbol=normalize_symbol(symbol.upper()),
        side=side,
        amount=float(amount),
        amount_mode=amount_mode,
        leverage=eff_leverage,
        sl_price=sl_price,
        tp_price=tp_price,
        trailing_stop=trailing_stop,
        order_type=order_type,
        entry_price=entry_price,
        margin_type=margin_type,
        reduce_only=reduce_only,
        market_type=config.market_type,
    )


def validate_draft(user_id: int, draft: LiveOrderDraft) -> dict:
    if draft.market_type not in ("spot", "futures"):
        raise BinanceClientError(f"Type de marché non supporté : {draft.market_type}")
    if draft.market_type != "futures" and draft.side == "SELL" and not draft.reduce_only:
        raise BinanceClientError("SHORT non supporté en Spot standard. Utilise Futures.")
    if draft.amount_mode != "risk" and draft.amount <= 0:
        raise BinanceClientError("Le montant doit être supérieur à 0.")

    # 1. Ouverture (non reduce_only) sans sl_price -> refus
    if not draft.reduce_only and (draft.sl_price is None or float(draft.sl_price) <= 0):
        raise BinanceClientError("Un Stop-Loss (sl_price) est obligatoire pour ouvrir une position.")

    config = get_config(user_id)

    # 2. Symbole in DOCUMENTED_SYMBOLS et autorisé par check_symbol_allowed
    norm_symbol = normalize_symbol(draft.symbol.upper())
    draft.symbol = norm_symbol
    if norm_symbol not in DOCUMENTED_SYMBOLS:
        raise BinanceClientError(f"Symbole {norm_symbol} non supporté (hors DOCUMENTED_SYMBOLS).")
    sym_check = check_symbol_allowed(config, norm_symbol)
    if not sym_check.allowed:
        raise BinanceClientError(sym_check.reason or f"Symbole {norm_symbol} non autorisé.")

    # 3. Levier <= config.leverage de l'utilisateur
    max_cfg_leverage = 1 if draft.market_type == "spot" else max(1, int(getattr(config, "leverage", 1) or 1))
    if draft.leverage < 1 or draft.leverage > max_cfg_leverage:
        raise BinanceClientError(
            f"Le levier demandé (x{draft.leverage}) dépasse le levier configuré (x{max_cfg_leverage})."
        )

    try:
        assert_trading_allowed(config, require_auto_trade=False)
    except SafetyError as e:
        raise BinanceClientError(str(e))
    if not draft.reduce_only:
        risk_check = check_can_open_position(
            user_id, config, draft.symbol, draft.side, require_auto_trade=False
        )
        if not risk_check.allowed:
            raise BinanceClientError(risk_check.reason or "Règle de risque non respectée.")

    client = _client_for_user(user_id, market_type=draft.market_type)
    max_leverage = _get_max_leverage(client, draft.symbol) if draft.market_type == "futures" else 1
    if max_leverage and draft.leverage > max_leverage:
        raise BinanceClientError(f"Levier x{draft.leverage} supérieur au maximum Binance autorisé pour {draft.symbol} (x{max_leverage}).")
    filters = get_symbol_filters(client, draft.symbol, draft.market_type)
    balance = get_account_balance(user_id, market_type=draft.market_type)
    if balance <= 0:
        raise BinanceClientError("Solde disponible insuffisant.")

    price = float(draft.entry_price or get_price(user_id, draft.symbol, draft.market_type))
    eff_lev = draft.leverage if draft.market_type == "futures" else 1
    step_size = filters.get("LOT_SIZE", {}).get("stepSize") or filters.get("MARKET_LOT_SIZE", {}).get("stepSize", "0.001")

    if draft.amount_mode == "risk":
        # Taille calculée par le risque : (solde × risk_per_trade%) / |prix − SL|, plafonnée à l'exposition max,
        # arrondie au pas Binance. SL arrondi au tick AVANT le calcul pour que le risque colle au SL réellement posé.
        tick_pre = _filter_float(filters, "PRICE_FILTER", "tickSize", 0.0)
        sl_for_sizing = _round_tick(draft.sl_price, tick_pre)
        sizing = compute_risk_based_quantity(
            balance=balance,
            risk_pct=float(getattr(config, "risk_per_trade", 1.0) or 1.0),
            entry_price=price,
            sl_price=float(sl_for_sizing or 0.0),
            leverage=eff_lev,
            market_type=draft.market_type,
            direction=draft.side,
            step_size=float(step_size),
            min_qty=_filter_float(filters, "LOT_SIZE", "minQty", 0.0),
            min_notional=_filter_float(filters, "MIN_NOTIONAL", "notional", 0.0)
            or _filter_float(filters, "NOTIONAL", "minNotional", 0.0),
        )
        if not sizing["ok"]:
            raise BinanceClientError(sizing["reason"] or "Taille de position impossible.")
        raw_qty = sizing["quantity"]
        margin_amount = sizing["margin_required"]
        available = get_available_balance(user_id, market_type=draft.market_type)
        if margin_amount > available:
            raise BinanceClientError(
                f"Marge requise ({margin_amount:.2f} USDT) supérieure au solde disponible ({available:.2f} USDT)."
            )
    else:
        margin_amount = balance * draft.amount / 100 if draft.amount_mode == "percentage" else draft.amount
        if margin_amount <= 0 or margin_amount > balance:
            raise BinanceClientError("Montant supérieur au solde disponible.")
        notional = margin_amount * eff_lev
        raw_qty = notional / price if price else 0.0
    quantity = round_step_size(raw_qty, step_size)
    min_qty = _filter_float(filters, "LOT_SIZE", "minQty", 0.0)
    min_notional = _filter_float(filters, "MIN_NOTIONAL", "notional", 0.0) or _filter_float(filters, "NOTIONAL", "minNotional", 0.0)
    tick_size = _filter_float(filters, "PRICE_FILTER", "tickSize", 0.0)

    if quantity <= 0 or (min_qty and quantity < min_qty):
        raise BinanceClientError("Taille de position inférieure au minimum Binance.")
    if min_notional and quantity * price < min_notional:
        raise BinanceClientError("Notional inférieur au minimum Binance.")

    entry_price = _round_tick(draft.entry_price, tick_size)
    sl_price = _round_tick(draft.sl_price, tick_size)
    tp_price = _round_tick(draft.tp_price, tick_size)

    if not draft.reduce_only:
        if sl_price is None or sl_price <= 0:
            raise BinanceClientError("Un Stop-Loss (sl_price) valide est obligatoire pour ouvrir une position.")
        if draft.side == "BUY":
            if sl_price >= price:
                raise BinanceClientError("SL incohérent avec un ordre BUY (attendu: SL < Prix).")
            if tp_price is not None and tp_price <= price:
                raise BinanceClientError("SL/TP incohérents avec un ordre BUY (attendu: SL < Prix < TP).")
        elif draft.side == "SELL":
            if sl_price <= price:
                raise BinanceClientError("SL incohérent avec un ordre SELL (attendu: Prix < SL).")
            if tp_price is not None and tp_price >= price:
                raise BinanceClientError("SL/TP incohérents avec un ordre SELL (attendu: TP < Prix < SL).")

        # 4. Perte au SL = |prix - SL| * quantité <= solde * risk_per_trade / 100
        sl_loss = abs(price - float(sl_price)) * quantity
        risk_pct = float(getattr(config, "risk_per_trade", 1.0) or 1.0)
        max_risk_usdt = balance * (risk_pct / 100.0)
        if sl_loss > max_risk_usdt + 1e-9:
            raise BinanceClientError(
                f"Perte potentielle au SL ({sl_loss:.2f} USDT) supérieure au risque maximum autorisé "
                f"({max_risk_usdt:.2f} USDT, soit {risk_pct}% du solde)."
            )

    return {
        "balance": balance,
        "margin_amount": margin_amount,
        "price": price,
        "quantity": quantity,
        "notional": quantity * price,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
    }


def _record_pending_client_order_id(user_id: int, key: Optional[str], client_order_id: str) -> str:
    """Enregistre ou relit le client_order_id avant l'envoi de l'ordre pour éviter tout doublon après timeout."""
    if key:
        existing = _get_idempotent_result(user_id, key)
        if isinstance(existing, dict) and existing.get("_pending_client_order_id"):
            return str(existing["_pending_client_order_id"])
        _save_idempotent_result(user_id, key, {"_pending_client_order_id": client_order_id})
    return client_order_id


def _is_order_filled(order: Optional[dict], default_if_missing_status: bool = True) -> bool:
    if not isinstance(order, dict):
        return False
    status = order.get("status")
    if status is None:
        return default_if_missing_status
    return str(status).upper() in ("FILLED", "PARTIALLY_FILLED")


def _place_live_futures_protection(
    client,
    symbol: str,
    opposite: str,
    checks: dict,
    result: dict,
) -> None:
    """Pose SL/TP d'une position Futures live via l'API Algo (les ordres conditionnels n'existent plus sur /order).

    Les niveaux sont recalés sur le prix réel d'exécution (slippage) en conservant leurs distances, puis
    enregistrés dans `checks` pour que le trade sauvegardé reflète les niveaux réellement posés.
    """
    need_sl = bool(checks.get("sl_price")) and not result.get("sl_order")
    need_tp = bool(checks.get("tp_price")) and not result.get("tp_order")
    if not (need_sl or need_tp):
        return

    filters = get_symbol_filters(client, symbol, "futures")
    position_direction = "BUY" if opposite == "SELL" else "SELL"
    fill_price = _extract_order_fill_price(result.get("order") or {}) or get_mark_price(client, symbol)
    sl, tp = rebase_protective_levels(
        position_direction, checks.get("price"), fill_price, checks.get("sl_price"), checks.get("tp_price")
    )
    checks["sl_price"], checks["tp_price"] = sl, tp

    warnings: list = []
    sl_oid, tp_oid = _place_futures_protective_orders(
        client, symbol, opposite, sl if need_sl else None, tp if need_tp else None, filters, warnings=warnings
    )
    if sl_oid:
        result["sl_order"] = {"orderId": sl_oid}
    if tp_oid:
        result["tp_order"] = {"orderId": tp_oid}
    if warnings:
        result.setdefault("warnings", []).extend(warnings)


def execute_draft(
    user_id: int,
    draft: LiveOrderDraft,
    execution_context: Optional[str] = None,
    *,
    pin: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    _pin_verified: bool = False,
) -> dict:
    if not _pin_verified and pin is not None:
        if not str(pin).strip():
            raise BinanceClientError("Code PIN de sécurité obligatoire pour exécuter un ordre réel.")
        ok_pin, pin_msg = security_manager.verify_code(user_id, str(pin).strip())
        if not ok_pin:
            raise BinanceClientError(pin_msg)

    _assert_order_context_allowed(user_id, execution_context, require_auto_trade=False)

    # 6. Exécution sous user_trading_lock(user_id) + 7. Idempotence
    with user_trading_lock(user_id):
        pending_coid: Optional[str] = None
        if idempotency_key:
            cached = _get_idempotent_result(user_id, idempotency_key)
            if isinstance(cached, dict):
                if cached.get("order") is not None:
                    return cached
                if cached.get("_pending_client_order_id"):
                    pending_coid = str(cached["_pending_client_order_id"])

        checks = validate_draft(user_id, draft)
        client = _client_for_user(user_id, market_type=draft.market_type)

        # Si un essai précédent a généré un client_order_id (ex: timeout), relire sur Binance avant tout nouvel essai
        if pending_coid:
            prior_order = _lookup_order_by_client_id(client, draft.symbol, pending_coid, draft.market_type)
            if prior_order and prior_order.get("orderId") is not None:
                recovered_res = {"checks": checks, "order": prior_order, "client_order_id": pending_coid}
                if idempotency_key:
                    _save_idempotent_result(user_id, idempotency_key, recovered_res)
                return recovered_res

        if not draft.reduce_only:
            remote_positions = get_open_binance_positions(user_id, market_type=draft.market_type)
            existing = [
                p for p in (remote_positions or [])
                if normalize_symbol(str(p.get("symbol", ""))) == draft.symbol
            ]
            if existing:
                raise BinanceClientError(
                    f"Ouverture refusée: position Binance existante sur {draft.symbol} ({existing})."
                )

        client_order_id = pending_coid or make_client_order_id("live", uuid.uuid4().hex)
        client_order_id = _record_pending_client_order_id(user_id, idempotency_key, client_order_id)

        result: dict = {"checks": checks, "client_order_id": client_order_id}
        opposite = "SELL" if draft.side == "BUY" else "BUY"
        opened_order: Optional[dict] = None
        main_order_sent = False

        try:
            if draft.market_type == "futures":
                try:
                    client.futures_change_margin_type(symbol=draft.symbol, marginType=draft.margin_type)
                except BinanceAPIException as e:
                    if getattr(e, "code", None) != -4046:  # No need to change margin type.
                        raise
                set_leverage(user_id, draft.symbol, draft.leverage)
                params = {
                    "symbol": draft.symbol,
                    "side": draft.side,
                    "type": draft.order_type,
                    "quantity": checks["quantity"],
                    "newClientOrderId": client_order_id,
                }
                if draft.order_type == "LIMIT":
                    params.update({"price": checks["entry_price"], "timeInForce": "GTC"})
                if draft.reduce_only:
                    params["reduceOnly"] = True

                main_order_sent = True
                order = client.futures_create_order(**params)
                opened_order = order
                result["order"] = order

                if not draft.reduce_only:
                    # Pour LIMIT Futures : ne poser STOP_MARKET / TAKE_PROFIT_MARKET que si l'ordre est déjà FILLED
                    should_place_protection = (
                        draft.order_type != "LIMIT"
                        or _is_order_filled(order, default_if_missing_status=False)
                    )
                    if should_place_protection:
                        _place_live_futures_protection(client, draft.symbol, opposite, checks, result)
            else:
                main_order_sent = True
                if draft.order_type == "LIMIT":
                    order = client.create_order(
                        symbol=draft.symbol,
                        side=draft.side,
                        type="LIMIT",
                        quantity=checks["quantity"],
                        price=checks["entry_price"],
                        timeInForce="GTC",
                        newClientOrderId=client_order_id,
                    )
                else:
                    order = client.create_order(
                        symbol=draft.symbol,
                        side=draft.side,
                        type="MARKET",
                        quantity=checks["quantity"],
                        newClientOrderId=client_order_id,
                    )
                opened_order = order
                result["order"] = order

                if not draft.reduce_only and draft.side == "BUY":
                    should_place_oco = (
                        draft.order_type != "LIMIT"
                        or _is_order_filled(order, default_if_missing_status=False)
                    )
                    if should_place_oco and checks.get("sl_price") and checks.get("tp_price"):
                        filters = get_symbol_filters(client, draft.symbol, "spot")
                        sl_oid, tp_oid, oco_order = _place_spot_oco_order(
                            client,
                            draft.symbol,
                            opposite,
                            float(checks["quantity"]),
                            float(checks["sl_price"]),
                            float(checks["tp_price"]),
                            filters,
                        )
                        result["oco_order"] = oco_order
                        if sl_oid:
                            result["sl_order"] = {"orderId": sl_oid}
                        if tp_oid:
                            result["tp_order"] = {"orderId": tp_oid}
                    elif should_place_oco and (checks.get("sl_price") or checks.get("tp_price")):
                        raise BinanceOrderException("Spot requiert sl_price et tp_price pour poser un ordre OCO.")
        except Exception as e:
            if not main_order_sent:
                logger.warning("Live order failed before send user=%s symbol=%s: %s", user_id, draft.symbol, getattr(e, "message", str(e)))
                raise BinanceClientError(f"Erreur Binance Live Trading : {getattr(e, 'message', str(e))}")

            if opened_order is None:
                opened_order = _lookup_order_by_client_id(client, draft.symbol, client_order_id, draft.market_type)
                if opened_order is not None:
                    result["order"] = opened_order

            if draft.market_type == "futures" and not draft.reduce_only:
                remote_pos = None
                remote_check_ok = False
                try:
                    positions = get_open_binance_positions(user_id, market_type="futures")
                    remote_check_ok = True
                    remote_pos = next(
                        (
                            p for p in (positions or [])
                            if normalize_symbol(str(p.get("symbol", ""))) == draft.symbol
                            and str(p.get("direction", "")).upper() == draft.side
                        ),
                        None,
                    )
                except Exception as pos_err:
                    logger.warning("Vérification position live après erreur sur %s (user=%s) impossible: %s", draft.symbol, user_id, pos_err)

                default_filled = (draft.order_type != "LIMIT")
                order_filled = _is_order_filled(opened_order, default_if_missing_status=default_filled)

                if remote_pos is not None or order_filled:
                    has_sl = bool(result.get("sl_order")) or not checks.get("sl_price")
                    has_tp = bool(result.get("tp_order")) or not checks.get("tp_price")
                    if not (has_sl and has_tp):
                        try:
                            _place_live_futures_protection(client, draft.symbol, opposite, checks, result)
                            has_sl = bool(result.get("sl_order")) or not checks.get("sl_price")
                            has_tp = bool(result.get("tp_order")) or not checks.get("tp_price")
                            if has_sl and has_tp and result.get("order") is not None:
                                _save_live_trade(user_id, draft, result)
                                if idempotency_key:
                                    _save_idempotent_result(user_id, idempotency_key, result)
                                return result
                        except Exception as prot_err:
                            logger.warning("Échec pose protection live de secours sur %s (user=%s): %s", draft.symbol, user_id, prot_err)

                    close_qty = float(remote_pos["quantity"]) if remote_pos and remote_pos.get("quantity") else checks["quantity"]
                    try:
                        client.futures_create_order(
                            symbol=draft.symbol,
                            side=opposite,
                            type="MARKET",
                            quantity=close_qty,
                            reduceOnly=True,
                        )
                    except Exception as close_err:
                        reason = (
                            f"Live position {draft.symbol} potentiellement sans protection après erreur ({getattr(e, 'message', str(e))}) "
                            f"et échec fermeture reduceOnly ({close_err})"
                        )
                        logger.critical("Live position %s sans protection pour user=%s: %s", draft.symbol, user_id, reason)
                        engage_safe_mode(user_id, reason)
                        raise BinanceClientError(
                            "Ordre principal ouvert mais protection SL/TP échouée; fermeture automatique impossible."
                        )
                    raise BinanceClientError("Ordre principal ouvert puis refermé car la protection SL/TP a échoué.")

                if not remote_check_ok and opened_order is None:
                    reason = f"État d'ordre live incertain après erreur réseau sur {draft.symbol} (clientOrderId={client_order_id}): {e}"
                    engage_safe_mode(user_id, reason)
                    raise BinanceClientError(f"Erreur réseau Live Trading sur {draft.symbol}; Safe Mode activé.")

            elif draft.market_type == "spot" and not draft.reduce_only and draft.side == "BUY":
                default_filled = (draft.order_type != "LIMIT")
                order_filled = _is_order_filled(opened_order, default_if_missing_status=default_filled)
                if order_filled:
                    if checks.get("sl_price") and checks.get("tp_price") and not (result.get("sl_order") and result.get("tp_order")):
                        try:
                            filters = get_symbol_filters(client, draft.symbol, "spot")
                            sl_oid, tp_oid, oco_order = _place_spot_oco_order(
                                client,
                                draft.symbol,
                                opposite,
                                float(checks["quantity"]),
                                float(checks["sl_price"]),
                                float(checks["tp_price"]),
                                filters,
                            )
                            result["oco_order"] = oco_order
                            if sl_oid:
                                result["sl_order"] = {"orderId": sl_oid}
                            if tp_oid:
                                result["tp_order"] = {"orderId": tp_oid}
                            if result.get("order") is not None and sl_oid and tp_oid:
                                _save_live_trade(user_id, draft, result)
                                if idempotency_key:
                                    _save_idempotent_result(user_id, idempotency_key, result)
                                return result
                        except Exception as oco_err:
                            logger.warning("Échec pose OCO live de secours sur %s (user=%s): %s", draft.symbol, user_id, oco_err)

                    try:
                        client.create_order(
                            symbol=draft.symbol,
                            side="SELL",
                            type="MARKET",
                            quantity=checks["quantity"],
                        )
                    except Exception as close_err:
                        reason = (
                            f"Position Spot live {draft.symbol} sans protection OCO après erreur ({getattr(e, 'message', str(e))}) "
                            f"et échec revente marché ({close_err})"
                        )
                        engage_safe_mode(user_id, reason)
                        raise BinanceClientError(
                            "Achat Spot exécuté mais protection OCO échouée; fermeture automatique impossible."
                        )
                    raise BinanceClientError("Achat Spot exécuté puis revendu car la protection OCO a échoué.")

                if opened_order is None:
                    reason = f"État d'ordre Spot live incertain après erreur réseau sur {draft.symbol} (clientOrderId={client_order_id}): {e}"
                    engage_safe_mode(user_id, reason)
                    raise BinanceClientError(f"Erreur réseau Spot Live Trading sur {draft.symbol}; Safe Mode activé.")

            logger.warning("Live order failed user=%s symbol=%s: %s", user_id, draft.symbol, getattr(e, "message", str(e)))
            raise BinanceClientError(f"Erreur Binance Live Trading : {getattr(e, 'message', str(e))}")

        _save_live_trade(user_id, draft, result)
        if idempotency_key:
            _save_idempotent_result(user_id, idempotency_key, result)
        return result


def _save_live_trade(user_id: int, draft: LiveOrderDraft, result: dict) -> None:
    order = result.get("order", {})
    checks = result["checks"]
    actual_price = _extract_order_fill_price(order) or checks["price"]
    client_oid = order.get("clientOrderId") or result.get("client_order_id")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trades (signal_id, user_id, symbol, direction, entry_price, sl_price, tp_price,
                    quantity, leverage, market_type, status, opened_at, binance_order_id,
                    binance_client_order_id, sl_order_id, tp_order_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', %s, %s, %s, %s, %s)
                """,
                (
                    "live_manual", user_id, draft.symbol, draft.side, actual_price, checks["sl_price"],
                    checks["tp_price"], checks["quantity"], draft.leverage, draft.market_type, time.time(),
                    str(order.get("orderId")) if order.get("orderId") else None,
                    client_oid,
                    str(result.get("sl_order", {}).get("orderId")) if result.get("sl_order") else None,
                    str(result.get("tp_order", {}).get("orderId")) if result.get("tp_order") else None,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def get_open_orders(user_id: int, symbol: Optional[str] = None) -> list[dict]:
    config = get_config(user_id)
    client = _client_for_user(user_id, market_type=config.market_type)
    try:
        if config.market_type == "futures":
            base = client.futures_get_open_orders(symbol=symbol) if symbol else client.futures_get_open_orders()
            return list(base) + futures_list_conditional_orders(client, symbol)  # + SL/TP (ordres Algo)
        return client.get_open_orders(symbol=symbol) if symbol else client.get_open_orders()
    except BinanceAPIException as e:
        raise BinanceClientError(f"Erreur Binance ordres ouverts : {e.message}")


def cancel_live_order(user_id: int, symbol: str, order_id: str, execution_context: Optional[str] = None, algo: Optional[bool] = None) -> None:
    _assert_order_context_allowed(
        user_id,
        execution_context,
        require_auto_trade=False,
        allow_under_safety_lock=True,
    )
    config = get_config(user_id)
    client = _client_for_user(user_id, market_type=config.market_type)
    try:
        if config.market_type == "futures":
            sym = normalize_symbol(symbol.upper())
            if algo:
                futures_cancel_conditional_order(client, sym, order_id)
            else:
                try:
                    client.futures_cancel_order(symbol=sym, orderId=order_id)
                except BinanceAPIException:
                    # Peut être un SL/TP (ordre Algo) : on tente l'annulation Algo avant d'échouer.
                    try:
                        futures_cancel_conditional_order(client, sym, order_id)
                    except Exception:
                        raise
        else:
            client.cancel_order(symbol=normalize_symbol(symbol.upper()), orderId=order_id)
    except BinanceAPIException as e:
        raise BinanceClientError(f"Erreur Binance annulation ordre : {e.message}")


def get_live_account(user_id: int) -> dict:
    config = get_config(user_id)
    return get_full_account_info(user_id, market_type=config.market_type)
