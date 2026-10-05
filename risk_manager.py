"""
risk_manager.py
----------------
Toute la logique de gestion du risque :
- calcul de la taille de position avec protection stricte contre la division par zéro (epsilon / tick_size)
- calcul dynamique du Stop Loss et du Trailing Stop basé sur l'ATR (Average True Range)
- vérification synchrone et asynchrone de la marge disponible (availableBalance) selon le levier
- vérification des limites (max positions, perte max journalière, cooldown)
- whitelist / blacklist de symboles normalisés
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from config import MAX_POSITION_EXPOSURE_PCT
from trading_config import TradingConfig, record_daily_loss
from binance_manager import (
    get_account_balance,
    get_available_balance,
    get_open_binance_positions,
    BinanceClientError,
)
from database import get_connection
from utils import normalize_symbol
from trading_safety import SafetyError, assert_trading_allowed

logger = logging.getLogger("risk_manager")

# Plafond d'exposition par position en % du capital total (défini dans config.py)
MAX_EXPOSURE_PCT: float = float(MAX_POSITION_EXPOSURE_PCT)
# Distance minimale en % entre le prix d'entrée et le Stop Loss
MIN_STOP_DISTANCE_PCT: float = 0.05
# Seuil mathématique absolu (epsilon) pour prévenir toute division par zéro
EPSILON: float = 1e-8


@dataclass
class RiskCheckResult:
    """Résultat structuré d'une vérification de règle de risque."""
    allowed: bool
    reason: Optional[str] = None


@dataclass
class MarginCheckResult:
    """Résultat détaillé de la vérification de marge avant émission d'ordre."""
    allowed: bool
    available_balance: float
    required_margin: float
    leverage: int
    reason: Optional[str] = None


def _max_position_notional(balance: float, leverage: int, market_type: str) -> float:
    """Retourne la taille notionnelle maximale autorisée pour le marché configuré.

    En Spot, une position consomme l'intégralité du notionnel sur le solde cash.
    En Futures, les positions utilisent la marge : le plafond d'exposition est donc
    converti en notionnel en multipliant par le levier configuré.
    """
    exposure_margin_cap = balance * (MAX_EXPOSURE_PCT / 100.0)
    if market_type == "futures":
        return exposure_margin_cap * max(int(leverage or 1), 1)
    return exposure_margin_cap


def compute_atr_dynamic_stop_loss(
    entry_price: float,
    direction: str,
    atr_value: float,
    atr_multiplier: float = 1.5,
    tick_size: float = EPSILON,
) -> float:
    """Calcule un prix de Stop Loss dynamique basé sur l'ATR (Average True Range)
    au lieu d'utiliser un pourcentage statique arbitraire.

    Garantit que la distance du Stop Loss est au moins supérieure à max(tick_size, EPSILON)
    et respecte MIN_STOP_DISTANCE_PCT.
    """
    if entry_price <= 0:
        raise ValueError("Le prix d'entrée doit être strictement positif.")
    if atr_value <= 0 or atr_multiplier <= 0:
        raise ValueError("La valeur de l'ATR et son multiplicateur doivent être strictement positifs.")

    min_distance = max(
        float(tick_size or EPSILON),
        EPSILON,
        entry_price * (MIN_STOP_DISTANCE_PCT / 100.0),
    )
    raw_distance = atr_value * atr_multiplier
    effective_distance = max(raw_distance, min_distance)

    side = (direction or "BUY").upper()
    if side == "BUY":
        sl_price = entry_price - effective_distance
        if sl_price <= 0:
            sl_price = max(entry_price * 0.01, EPSILON)
        return sl_price
    elif side == "SELL":
        return entry_price + effective_distance
    else:
        raise ValueError(f"Direction de trade invalide pour le calcul SL dynamique : {direction}")


def verify_margin_availability(
    user_id: int,
    notional: float,
    leverage: int = 1,
    market_type: str = "futures",
    asset: str = "USDT",
) -> MarginCheckResult:
    """Vérifie de manière synchrone le solde disponible (availableBalance) sur Binance
    et calcule la marge requise en fonction du levier avant l'émission d'un ordre.
    """
    eff_leverage = max(int(leverage or 1), 1) if market_type == "futures" else 1
    required_margin = notional / eff_leverage if eff_leverage > 0 else notional

    available = float(get_available_balance(user_id, market_type=market_type, asset=asset))
    if required_margin > available:
        reason = (
            f"Marge disponible insuffisante ({available:.2f} {asset} < {required_margin:.2f} {asset}) "
            f"pour un notionnel de {notional:.2f} {asset} (levier x{eff_leverage})."
        )
        return MarginCheckResult(
            allowed=False,
            available_balance=available,
            required_margin=required_margin,
            leverage=eff_leverage,
            reason=reason,
        )

    return MarginCheckResult(
        allowed=True,
        available_balance=available,
        required_margin=required_margin,
        leverage=eff_leverage,
    )


async def verify_margin_availability_async(
    user_id: int,
    notional: float,
    leverage: int = 1,
    market_type: str = "futures",
    asset: str = "USDT",
) -> MarginCheckResult:
    """Version asynchrone non-bloquante de la vérification de marge disponible."""
    return await asyncio.to_thread(
        verify_margin_availability,
        user_id=user_id,
        notional=notional,
        leverage=leverage,
        market_type=market_type,
        asset=asset,
    )


def _log_position_sizing_diagnostics(
    *,
    user_id: int,
    market_type: str,
    balance: float,
    risk_pct: float,
    risk_amount: Optional[float],
    leverage: int,
    entry_price: float,
    sl_price: float,
    price_distance: Optional[float],
    stop_distance_pct: Optional[float],
    quantity: Optional[float],
    notional: Optional[float],
    max_notional: Optional[float],
    available_margin: Optional[float] = None,
    required_margin: Optional[float] = None,
    atr_value: Optional[float] = None,
    tick_size: float = EPSILON,
    decision: str = "",
) -> None:
    """Journalise de manière détaillée tous les paramètres du dimensionnement de position."""
    logger.info(
        "===== Position sizing =====\n"
        "user_id=%s market_type=%s\n"
        "Balance: %.8f USDT\n"
        "Capital utilise: %.8f USDT\n"
        "Risque: %.4f%%\n"
        "Montant a risquer: %s USDT\n"
        "Levier: x%s\n"
        "Entry: %.8f\n"
        "Stop Loss: %.8f\n"
        "Distance SL: %s (seuil min epsilon/tick=%.8f)\n"
        "Distance SL %%: %s\n"
        "ATR: %s\n"
        "Quantite calculee: %s\n"
        "Notional: %s USDT\n"
        "Plafond exposition: %s USDT (MAX_POSITION_EXPOSURE_PCT=%.4f%%)\n"
        "Marge disponible: %s USDT\n"
        "Marge requise: %s USDT\n"
        "Decision: %s",
        user_id,
        market_type,
        balance,
        balance,
        risk_pct,
        f"{risk_amount:.8f}" if risk_amount is not None else "N/A",
        leverage,
        entry_price,
        sl_price,
        f"{price_distance:.8f}" if price_distance is not None else "N/A",
        tick_size,
        f"{stop_distance_pct:.8f}%" if stop_distance_pct is not None else "N/A",
        f"{atr_value:.8f}" if atr_value is not None else "non fourni a calculate_position_size",
        f"{quantity:.12f}" if quantity is not None else "N/A",
        f"{notional:.8f}" if notional is not None else "N/A",
        f"{max_notional:.8f}" if max_notional is not None else "N/A",
        MAX_EXPOSURE_PCT,
        f"{available_margin:.8f}" if available_margin is not None else "N/A",
        f"{required_margin:.8f}" if required_margin is not None else "N/A",
        decision,
    )


def count_local_open_positions(user_id: int) -> int:
    """Compte le nombre de positions actuellement ouvertes dans la base locale."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM trades WHERE user_id = %s AND status = 'open'",
                (user_id,),
            )
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def count_duplicate_open_positions(user_id: int, symbol: str, direction: str) -> int:
    """Vérifie si une position identique (même symbole et direction) est déjà ouverte."""
    norm_sym = normalize_symbol(symbol)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM trades
                WHERE user_id = %s AND status = 'open' AND symbol = %s AND direction = %s
                """,
                (user_id, norm_sym, direction.upper()),
            )
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def count_open_positions(user_id: int) -> int:
    """Alias retournant le nombre de positions locales ouvertes."""
    return count_local_open_positions(user_id)


def count_remote_open_positions(user_id: int, market_type: str = "futures") -> int:
    """Compte le nombre de positions réellement ouvertes sur le compte Binance Futures."""
    if market_type != "futures":
        return 0
    return len(get_open_binance_positions(user_id, market_type=market_type))


def get_last_trade_time(user_id: int) -> Optional[float]:
    """Récupère le timestamp d'ouverture du dernier trade de l'utilisateur."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT opened_at FROM trades WHERE user_id = %s ORDER BY opened_at DESC LIMIT 1",
                (user_id,),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None
    finally:
        conn.close()


def check_symbol_allowed(config: TradingConfig, symbol: str) -> RiskCheckResult:
    """Vérifie si le symbole normalisé est autorisé par la whitelist et la blacklist."""
    try:
        normalized_symbol = normalize_symbol(symbol or "")
    except ValueError as e:
        return RiskCheckResult(False, str(e))

    blacklist = {normalize_symbol(s) for s in (config.symbol_blacklist or []) if s}
    whitelist = {normalize_symbol(s) for s in (config.symbol_whitelist or []) if s}

    if blacklist and normalized_symbol in blacklist:
        return RiskCheckResult(False, f"{normalized_symbol} est dans ta blacklist.")
    if whitelist and normalized_symbol not in whitelist:
        return RiskCheckResult(False, f"{normalized_symbol} n'est pas dans ta whitelist.")
    return RiskCheckResult(True)


def check_can_open_position(
    user_id: int,
    config: TradingConfig,
    symbol: str,
    direction: Optional[str] = None,
) -> RiskCheckResult:
    """Vérifie toutes les règles de gestion du risque avant d'ouvrir une nouvelle position."""
    try:
        assert_trading_allowed(config)
    except SafetyError as e:
        return RiskCheckResult(False, str(e))

    symbol_check = check_symbol_allowed(config, symbol)
    if not symbol_check.allowed:
        return symbol_check

    norm_symbol = normalize_symbol(symbol)
    if direction and count_duplicate_open_positions(user_id, norm_symbol, direction) > 0:
        return RiskCheckResult(
            False,
            f"Une position {direction.upper()} est déjà ouverte sur {norm_symbol}.",
        )

    local_open_count = count_local_open_positions(user_id)
    remote_open_count = 0
    if config.market_type == "futures":
        try:
            remote_open_count = count_remote_open_positions(user_id, config.market_type)
        except BinanceClientError as e:
            logger.warning("Risk check blocked user=%s: Binance positions unavailable: %s", user_id, e)
            return RiskCheckResult(
                False,
                "Positions Binance impossibles à vérifier, ouverture suspendue par sécurité.",
            )
        if remote_open_count != local_open_count:
            logger.warning(
                "Risk divergence user=%s local_open=%s remote_open=%s — blocking new position opening",
                user_id,
                local_open_count,
                remote_open_count,
            )
            return RiskCheckResult(
                False,
                "Divergence positions locales/Binance, ouverture suspendue par sécurité.",
            )

    open_count = max(local_open_count, remote_open_count)
    if open_count >= config.max_positions:
        return RiskCheckResult(
            False,
            f"Nombre max de positions atteint ({config.max_positions}).",
        )

    if config.daily_loss_accum and config.max_daily_loss:
        try:
            balance = get_account_balance(user_id, market_type=config.market_type)
        except Exception:
            balance = None
        if balance and balance > 0:
            loss_pct = (config.daily_loss_accum / balance) * 100.0
            if loss_pct >= config.max_daily_loss:
                return RiskCheckResult(
                    False,
                    f"Perte quotidienne max atteinte ({config.max_daily_loss}%). "
                    f"Trading suspendu jusqu'à demain.",
                )

    if config.cooldown_seconds:
        last_trade = get_last_trade_time(user_id)
        if last_trade and (time.time() - last_trade) < config.cooldown_seconds:
            remaining = int(config.cooldown_seconds - (time.time() - last_trade))
            return RiskCheckResult(False, f"Cooldown actif, réessaie dans {remaining}s.")

    return RiskCheckResult(True)


def calculate_position_size(
    user_id: int,
    config: TradingConfig,
    entry_price: float,
    sl_price: Optional[float],
    market_type: str = "futures",
    *,
    atr_value: Optional[float] = None,
    atr_multiplier: float = 1.5,
    direction: str = "BUY",
    tick_size: float = EPSILON,
) -> float:
    """Calcule la taille de position basée sur le risque en % du capital et la distance au SL.

    Sécurités intégrées :
    1. Si `sl_price` est absent mais `atr_value` est fourni, calcule un Stop Loss dynamique basé sur l'ATR.
    2. Protection stricte contre la division par zéro : vérifie que `entry_price > EPSILON` et que
       `|entry_price - sl_price| >= max(tick_size, EPSILON)`.
    3. Vérification de la marge requise vs `availableBalance` en tenant compte du levier avant validation.
    """
    balance = float(get_account_balance(user_id, market_type=market_type))
    leverage = max(int(config.leverage or 1), 1)
    effective_tick = max(float(tick_size or EPSILON), EPSILON)

    if balance <= 0:
        _log_position_sizing_diagnostics(
            user_id=user_id,
            market_type=market_type,
            balance=balance,
            risk_pct=config.risk_per_trade,
            risk_amount=None,
            leverage=leverage,
            entry_price=entry_price,
            sl_price=sl_price or 0.0,
            price_distance=None,
            stop_distance_pct=None,
            quantity=None,
            notional=None,
            max_notional=None,
            atr_value=atr_value,
            tick_size=effective_tick,
            decision="REFUS: solde insuffisant ou introuvable",
        )
        raise ValueError("Solde insuffisant ou introuvable sur le compte Binance.")

    if entry_price is None or entry_price <= effective_tick:
        raise ValueError(f"Prix d'entrée invalide ({entry_price}).")

    # Calcul dynamique du SL basé sur l'ATR si aucun SL valide n'est fourni
    if (sl_price is None or sl_price <= 0) and atr_value is not None and atr_value > 0:
        sl_price = compute_atr_dynamic_stop_loss(
            entry_price=entry_price,
            direction=direction,
            atr_value=atr_value,
            atr_multiplier=atr_multiplier,
            tick_size=effective_tick,
        )

    if sl_price is None or sl_price <= 0:
        raise ValueError("Stop Loss invalide ou manquant (aucun ATR fourni pour le calcul dynamique).")

    risk_amount = balance * (config.risk_per_trade / 100.0)
    price_distance = abs(entry_price - sl_price)
    max_notional = _max_position_notional(balance, leverage, market_type)

    # Protection rigoureuse contre la division par zéro via epsilon / tick_size
    if price_distance < effective_tick:
        _log_position_sizing_diagnostics(
            user_id=user_id,
            market_type=market_type,
            balance=balance,
            risk_pct=config.risk_per_trade,
            risk_amount=risk_amount,
            leverage=leverage,
            entry_price=entry_price,
            sl_price=sl_price,
            price_distance=price_distance,
            stop_distance_pct=None,
            quantity=None,
            notional=None,
            max_notional=max_notional,
            atr_value=atr_value,
            tick_size=effective_tick,
            decision="REFUS: distance SL nulle ou inferieure au tick_size/epsilon",
        )
        raise ValueError(
            f"SL invalide : distance ({price_distance:.10f}) nulle ou inférieure au seuil minimal ({effective_tick:.10f})."
        )

    stop_distance_pct = (price_distance / entry_price) * 100.0
    if stop_distance_pct < MIN_STOP_DISTANCE_PCT:
        _log_position_sizing_diagnostics(
            user_id=user_id,
            market_type=market_type,
            balance=balance,
            risk_pct=config.risk_per_trade,
            risk_amount=risk_amount,
            leverage=leverage,
            entry_price=entry_price,
            sl_price=sl_price,
            price_distance=price_distance,
            stop_distance_pct=stop_distance_pct,
            quantity=None,
            notional=None,
            max_notional=max_notional,
            atr_value=atr_value,
            tick_size=effective_tick,
            decision="REFUS: SL trop serre",
        )
        raise ValueError(
            f"SL trop serré ({stop_distance_pct:.4f}%). Minimum configuré: {MIN_STOP_DISTANCE_PCT}%."
        )

    quantity = risk_amount / price_distance
    notional = quantity * entry_price

    capped = False
    if notional > max_notional:
        quantity = max_notional / entry_price
        notional = quantity * entry_price
        capped = True

    # Vérification de la marge disponible en fonction du levier avant émission d'ordre
    margin_check = verify_margin_availability(
        user_id=user_id,
        notional=notional,
        leverage=leverage if market_type == "futures" else 1,
        market_type=market_type,
    )

    if not margin_check.allowed:
        decision_msg = (
            "REFUS: marge disponible insuffisante"
            if market_type == "futures"
            else "REFUS: solde cash Spot insuffisant"
        )
        _log_position_sizing_diagnostics(
            user_id=user_id,
            market_type=market_type,
            balance=balance,
            risk_pct=config.risk_per_trade,
            risk_amount=risk_amount,
            leverage=margin_check.leverage,
            entry_price=entry_price,
            sl_price=sl_price,
            price_distance=price_distance,
            stop_distance_pct=stop_distance_pct,
            quantity=quantity,
            notional=notional,
            max_notional=max_notional,
            available_margin=margin_check.available_balance,
            required_margin=margin_check.required_margin,
            atr_value=atr_value,
            tick_size=effective_tick,
            decision=decision_msg,
        )
        if market_type == "futures":
            raise ValueError(
                f"Marge disponible insuffisante ({margin_check.available_balance:.2f} USDT < {margin_check.required_margin:.2f} USDT)."
            )
        raise ValueError(
            f"Solde disponible Spot insuffisant ({margin_check.available_balance:.2f} USDT < {notional:.2f} USDT)."
        )

    decision = (
        "ACCEPTE (Position size capped by maximum exposure)"
        if capped
        else "ACCEPTE"
    )
    _log_position_sizing_diagnostics(
        user_id=user_id,
        market_type=market_type,
        balance=balance,
        risk_pct=config.risk_per_trade,
        risk_amount=risk_amount,
        leverage=leverage,
        entry_price=entry_price,
        sl_price=sl_price,
        price_distance=price_distance,
        stop_distance_pct=stop_distance_pct,
        quantity=quantity,
        notional=notional,
        max_notional=max_notional,
        available_margin=margin_check.available_balance,
        required_margin=margin_check.required_margin,
        atr_value=atr_value,
        tick_size=effective_tick,
        decision=decision,
    )
    return quantity


async def calculate_position_size_async(
    user_id: int,
    config: TradingConfig,
    entry_price: float,
    sl_price: Optional[float],
    market_type: str = "futures",
    *,
    atr_value: Optional[float] = None,
    atr_multiplier: float = 1.5,
    direction: str = "BUY",
    tick_size: float = EPSILON,
) -> float:
    """Version asynchrone de `calculate_position_size` pour ne pas bloquer l'event loop."""
    return await asyncio.to_thread(
        calculate_position_size,
        user_id,
        config,
        entry_price,
        sl_price,
        market_type,
        atr_value=atr_value,
        atr_multiplier=atr_multiplier,
        direction=direction,
        tick_size=tick_size,
    )


def record_trade_loss(user_id: int, loss_usdt: float) -> float:
    """À appeler quand un trade se ferme en perte (SL touché) pour mettre à jour le cumul journalier."""
    if loss_usdt <= 0:
        return 0.0
    return record_daily_loss(user_id, loss_usdt)
