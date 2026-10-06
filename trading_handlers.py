"""
trading_handlers.py
---------------------
Toutes les commandes Telegram utilisateur pour le module AutoTrade, ainsi que
le routeur de callbacks pour les boutons (menu_autotrade, menu_positions, etc.)
et la confirmation des signaux en mode semi-automatique.
"""

import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from trading_config import get_config, update_config, save_binance_credentials
from binance_manager import (
    test_connection, get_full_account_info, get_open_binance_positions,
    BinanceClientError, ORDER_CONTEXT_MANUAL_AUTHENTICATED,
)
from position_manager import get_open_trades, close_trade_manual, emergency_stop_all
from execution_engine import execute_signal, mark_signal_status, validate_signal_for_execution, insert_trade_row
from database import get_connection
from trading_logger import get_trading_logger
from security_manager import has_security_code, set_initial_code, change_code, verify_code
from utils import escape_markdown, normalize_symbol

logger = get_trading_logger("trading_handlers")


async def _safe_edit(query, text: str, **kwargs):
    """Édite un message Telegram en ignorant l'erreur 'Message is not modified'."""
    try:
        return await query.edit_message_text(text, **kwargs)
    except BadRequest as exc:
        if "Message is not modified" in str(exc):
            return None
        raise


def _is_user_allowed(user_id: int) -> bool:
    """Le module doit être désactivable proprement si l'utilisateur n'a pas configuré ses clés."""
    from trading_config import get_binance_credentials
    creds = get_binance_credentials(user_id)
    return creds is not None and creds.get("api_key") and creds.get("is_valid")


NO_KEYS_MESSAGE = (
    "🔑 Tu n'as pas encore configuré tes clés API Binance.\n"
    "Utilise /setapikeys <api_key> <api_secret> pour les ajouter "
    "(en message privé uniquement, jamais dans un groupe)."
)


async def _delete_sensitive_command_message(update: Update, action: str) -> None:
    """Best-effort deletion for Telegram messages that may contain secrets.

    The secret value is never logged. If Telegram refuses deletion (permissions,
    age, chat type), only metadata is logged and the flow continues safely.
    """
    message = getattr(update, "message", None)
    if not message:
        return
    try:
        await message.delete()
    except Exception as exc:
        logger.warning(
            "Sensitive command message deletion failed action=%s chat_id=%s message_id=%s error_type=%s",
            action,
            getattr(getattr(message, "chat", None), "id", None),
            getattr(message, "message_id", None),
            type(exc).__name__,
        )


def _pop_security_code(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    if not context.args:
        return None
    candidate = context.args[-1].strip()
    return candidate if len(candidate) == 6 else None


def _sensitive_authorized(user_id: int, context: ContextTypes.DEFAULT_TYPE, *, require_pin: bool = False) -> tuple[bool, str]:
    """Vérifie le code PIN à 6 chiffres lorsqu'un PIN est configuré ou requis."""
    if not require_pin and not has_security_code(user_id):
        return True, ""
    code = _pop_security_code(context)
    if not code:
        if not has_security_code(user_id):
            return False, "Aucun code de sécurité configuré. Définis d'abord un PIN à 6 chiffres avec /setsecurity <code_6_chiffres>."
        return False, "Code de sécurité à 6 chiffres requis en dernier argument."
    ok, msg = verify_code(user_id, code)
    if ok and context.args and context.args[-1].strip() == code:
        context.args = list(context.args[:-1])
    return ok, msg


def _require_pin(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> tuple[bool, str]:
    return _sensitive_authorized(update.effective_user.id, context, require_pin=False)


def _parse_on_off(value: str) -> bool | None:
    normalized = value.lower()
    if normalized in ("on", "true", "1", "yes", "oui", "activer", "enable"):
        return True
    if normalized in ("off", "false", "0", "no", "non", "désactiver", "desactiver", "disable"):
        return False
    return None


async def cmd_setsecurity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configure ou modifie le code PIN de sécurité à 6 chiffres."""
    user_id = update.effective_user.id
    await _delete_sensitive_command_message(update, "setsecurity")
    if not context.args:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🔐 *Code de sécurité (PIN 6 chiffres)*\n"
                "• Premier code : `/setsecurity <nouveau_code_6_chiffres>`\n"
                "• Changer le code : `/setsecurity <ancien_code> <nouveau_code>`"
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if len(context.args) == 1:
        ok, msg = set_initial_code(user_id, context.args[0])
    else:
        ok, msg = change_code(user_id, context.args[0], context.args[1])
    prefix = "✅" if ok else "❌"
    await context.bot.send_message(chat_id=user_id, text=f"{prefix} {msg}")


async def cmd_clearsafe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /clearsafe <code_securite> — lève safety_lock et safety_warn (protégée par PIN)."""
    user_id = update.effective_user.id
    await _delete_sensitive_command_message(update, "clearsafe")
    ok, msg = _sensitive_authorized(user_id, context, require_pin=True)
    if not ok:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🔐 Déverrouillage refusé : {msg}\nUsage : /clearsafe <code_securite>",
        )
        return

    update_config(
        user_id,
        safety_lock=False,
        safety_lock_reason=None,
        safety_lock_at=None,
        safety_warn=False,
        safety_warn_reason=None,
        safety_warn_at=None,
    )
    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "✅ Safe Mode et avertissements de sécurité levés avec succès.\n"
            "• safety_lock : INACTIF\n"
            "• safety_warn : INACTIF\n"
            "Note : si tu souhaites réactiver l'ouverture automatique d'ordres, utilise /autotrade on."
        ),
    )


async def cmd_safestatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande publique /safestatus — affiche l'état complet safety_lock / safety_warn et les divergences."""
    user_id = update.effective_user.id
    config = get_config(user_id)
    now = time.time()

    def _fmt_ts(ts: float | None) -> str:
        if not ts:
            return "—"
        try:
            return datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return str(ts)

    lock_state = "🔴 ACTIF (Verrouillage Critique)" if config.safety_lock else "🟢 INACTIF"
    ttl = int(getattr(config, "safety_lock_ttl_seconds", 3600) or 0)
    if config.safety_lock and config.safety_lock_at and ttl > 0:
        rem = max(0, int((float(config.safety_lock_at) + ttl) - now))
        ttl_str = f"{rem}s (~{max(1, rem // 60)} min)" if rem > 0 else "Expiré (downgrade auto au prochain check)"
    elif ttl == 0:
        ttl_str = "Désactivé (strict)"
    else:
        ttl_str = f"{ttl}s"

    warn_state = "🟠 ACTIF (Avertissement Temporaire)" if config.safety_warn else "🟢 INACTIF"

    lines = [
        "🛡️ *État du Système de Sécurité (Safe Mode)*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"• *Verrouillage Critique (safety_lock)* : {lock_state}",
        f"  Raison : `{escape_markdown(config.safety_lock_reason or '—')}`",
        f"  Horodatage : `{_fmt_ts(config.safety_lock_at)}`",
        f"  TTL restant : `{ttl_str}`",
        "",
        f"• *Avertissement (safety_warn)* : {warn_state}",
        f"  Raison : `{escape_markdown(config.safety_warn_reason or '—')}`",
        f"  Horodatage : `{_fmt_ts(config.safety_warn_at)}`",
    ]

    if config.safety_lock:
        lines.append("\n🔍 *Positions Binance divergentes :*")
        try:
            local_trades = [t for t in get_open_trades(user_id) if t["market_type"] == "futures"]
            local_keys = {(normalize_symbol(t["symbol"]), str(t["direction"]).upper()) for t in local_trades}
            remote_positions = get_open_binance_positions(user_id, market_type="futures")
            remote_keys = {(normalize_symbol(p["symbol"]), str(p["direction"]).upper()): p for p in remote_positions}

            divergent = []
            for k, pos in remote_keys.items():
                if k not in local_keys:
                    divergent.append(f"  - `{k[0]}` {k[1]} qty={pos['quantity']} (présente sur Binance, absente localement)")
            for k in local_keys:
                if k not in remote_keys:
                    divergent.append(f"  - `{k[0]}` {k[1]} (présente localement, absente sur Binance)")

            if divergent:
                lines.extend(divergent)
            else:
                lines.append("  Aucune divergence active détectée actuellement.")
        except Exception as e:
            lines.append(f"  Impossible de vérifier les positions Binance : `{escape_markdown(str(e))}`")

    lines.append("\n💡 *Actions recommandées :*")
    if config.safety_lock:
        if ttl > 0 and config.safety_lock_at:
            rem_min = max(1, int(max(0, (float(config.safety_lock_at) + ttl) - now) // 60))
            lines.append(f"  • Vérifier vos positions sur Binance puis exécuter `/clearsafe <code_securite>`")
            lines.append(f"  • Ou attendre ~{rem_min} minute(s) pour le downgrade automatique en avertissement.")
        else:
            lines.append("  • Vérifier vos positions sur Binance puis exécuter `/clearsafe <code_securite>`.")
    elif config.safety_warn:
        lines.append("  • Aucune action urgente requise : l'avertissement s'effacera automatiquement au prochain cycle réussi.")
        lines.append("  • Pour acquitter manuellement : `/clearsafe <code_securite>`.")
    else:
        lines.append("  • Tout est nominal. Aucune action requise.")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

# ---------------------------------------------------------------------------
# Commandes utilisateur
# ---------------------------------------------------------------------------

async def cmd_setapikeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await _delete_sensitive_command_message(update, "setapikeys")
    ok, msg = _sensitive_authorized(user_id, context)
    if not ok:
        await update.message.reply_text(f"🔐 {msg}")
        return

    if len(context.args) < 2:
        await context.bot.send_message(
            chat_id=user_id,
            text="Usage : /setapikeys <api_key> <api_secret>\n(Envoie ce message en privé uniquement.)",
        )
        return

    api_key, api_secret = context.args[0], context.args[1]
    config = get_config(user_id)
    save_binance_credentials(user_id, api_key, api_secret, testnet=config.testnet)

    try:
        test_connection(user_id)
        await context.bot.send_message(chat_id=user_id, text="✅ Clés API validées et enregistrées.")
    except BinanceClientError as e:
        await context.bot.send_message(chat_id=user_id, text=f"⚠️ Clés enregistrées mais la connexion a échoué : {e}")


async def cmd_autotrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche le menu AutoTrade (cohérent avec sa description dans /help et le menu natif Telegram).
    Le basculement ON/OFF se fait via le bouton dédié dans ce menu, plutôt qu'en aveugle à chaque appel."""
    user_id = update.effective_user.id
    if not _is_user_allowed(user_id):
        await update.message.reply_text(NO_KEYS_MESSAGE)
        return

    if context.args and context.args[0].lower() in ("on", "off"):
        desired = context.args[0].lower() == "on"
        if desired:
            await _delete_sensitive_command_message(update, "autotrade_on")
            ok, msg = _sensitive_authorized(user_id, context)
            if not ok:
                await update.message.reply_text(f"🔐 {msg}")
                return
            update_config(user_id, auto_trade=True)
            await update.message.reply_text("✅ AutoTrade activé.")
        else:
            update_config(user_id, auto_trade=False)
            await update.message.reply_text("❌ AutoTrade désactivé.")
        return

    text, keyboard = _build_autotrade_menu(user_id)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)




async def cmd_periodic_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Active/désactive l'analyse automatique du marché Binance sans activer AutoTrade, ou lance un scan immédiat."""
    user_id = update.effective_user.id

    config = get_config(user_id)
    if not context.args or context.args[0].lower() in ("status", "etat", "état"):
        status = "ON ✅" if config.periodic_analysis_enabled else "OFF ❌"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{'🔴 Désactiver' if config.periodic_analysis_enabled else '🟢 Activer'} l'Analyse Périodique", callback_data="toggle_periodic_analysis")],
            [InlineKeyboardButton("🚀 Lancer une analyse maintenant", callback_data="run_periodic_analysis_now")],
            [InlineKeyboardButton("⚙️ Configurer Intervalle / TF / Style", callback_data="menu_analysis_config")],
        ])
        await update.message.reply_text(
            "📊 *Analyse Périodique du Marché*\n"
            f"• État : *{status}*\n"
            f"• Intervalle : *{config.analysis_interval_minutes} min*\n"
            f"• Timeframe : *{escape_markdown(config.analysis_timeframe)}*\n"
            f"• Style : *{escape_markdown(config.trading_style)}*\n\n"
            "Commandes rapides :\n"
            "• /periodic\\_analysis `on` (ou `on 5` / `on 10`)\n"
            "• /periodic\\_analysis `off`\n"
            "• /periodic\\_analysis `now` (scan immédiat)",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    action = context.args[0].lower()
    if action in ("now", "run", "scan", "test"):
        msg = await update.message.reply_text("⏳ *Analyse périodique en cours...* Scan des opportunités du marché en direct.", parse_mode=ParseMode.MARKDOWN)
        from execution_engine import run_market_analysis_for_user
        report = await run_market_analysis_for_user(context, user_id, config.analysis_interval_minutes)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Relancer l'analyse", callback_data="run_periodic_analysis_now")],
            [InlineKeyboardButton("⚙️ Configuration Analyse Périodique", callback_data="menu_analysis_config")],
            [InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_back")],
        ])
        try:
            await msg.edit_text(report, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await msg.edit_text(report.replace("*", "").replace("`", "").replace("_", ""), reply_markup=kb)
        return

    if action not in ("on", "off"):
        await update.message.reply_text("Usage : /periodic_analysis on | /periodic_analysis on <5|10> | /periodic_analysis off | /periodic_analysis now")
        return

    if action == "off":
        update_config(user_id, periodic_analysis_enabled=False)
        await update.message.reply_text("📊 Analyse périodique désactivée.")
        return

    config = get_config(user_id)
    interval = config.analysis_interval_minutes
    if len(context.args) >= 2:
        try:
            interval = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Intervalle invalide. Utilise 5 ou 10 minutes.")
            return

    if interval not in (5, 10):
        await update.message.reply_text(
            "Intervalle non supporté à chaud. Utilise 5 ou 10 minutes pour garantir que le scheduler actif lance l'analyse."
        )
        return

    if config.safety_lock:
        update_config(
            user_id,
            periodic_analysis_enabled=True,
            analysis_interval_minutes=interval,
            auto_trade=False,
        )
        await update.message.reply_text(
            "✅ Analyse périodique activée en mode lecture seule (Safe Mode actif).\n"
            f"Le marché sera analysé automatiquement toutes les {interval} minutes."
        )
        return

    update_config(user_id, periodic_analysis_enabled=True, analysis_interval_minutes=interval)
    await update.message.reply_text(
        f"✅ Analyse périodique activée (toutes les {interval} minutes).\n"
        "💡 Tu peux aussi lancer un scan immédiat avec /periodic_analysis now ou depuis le bouton du menu."
    )


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    config = get_config(user_id)
    text = (
        f"⚙️ *Configuration de trading*\n\n"
        f"Mode auto : {'ON' if config.auto_trade else 'OFF'}\n"
        f"Marché : {config.market_type}\n"
        f"Style : {config.trading_style}\n"
        f"Timeframe analyse : {config.analysis_timeframe}\n"
        f"Analyse auto : toutes les {config.analysis_interval_minutes} min\n"
        f"Levier : x{config.leverage}\n"
        f"Risque par trade : {config.risk_per_trade}%\n"
        f"Max positions : {config.max_positions}\n"
        f"Score minimum : {config.min_score}\n"
        f"Perte max/jour : {config.max_daily_loss}%\n"
        f"Trailing stop : {'ON' if config.trailing_stop else 'OFF'} ({config.trailing_stop_pct}%)"
        f"{' — déplacement auto futures non disponible' if config.market_type == 'futures' else ''}\n"
        f"DCA : {'configuré mais non disponible' if config.dca_enabled else 'OFF'} ({config.dca_steps} étapes, {config.dca_step_pct}%)\n"
        f"Cooldown : {config.cooldown_seconds}s\n"
        f"Testnet : {'OUI' if config.testnet else 'NON — argent réel'}\n"
        f"Whitelist : {', '.join(config.symbol_whitelist) or '—'}\n"
        f"Blacklist : {', '.join(config.symbol_blacklist) or '—'}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    trades = get_open_trades(user_id)
    if not trades:
        await update.message.reply_text("Aucune position ouverte actuellement.")
        return

    lines = ["📈 *Positions ouvertes*\n"]
    for t in trades:
        lines.append(
            f"#{t['id']} `{t['symbol']}` {t['direction']} — qty {t['quantity']} "
            f"(SL {t['sl_price']} / TP {t['tp_price']})"
        )
    lines.append("\nUtilise /close <id> pour fermer une position.")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await _delete_sensitive_command_message(update, "close")
    ok, msg = _sensitive_authorized(user_id, context)
    if not ok:
        await update.message.reply_text(f"🔐 {msg}")
        return
    if not context.args:
        await update.message.reply_text("Usage : /close <id_position>")
        return

    try:
        trade_id = int(context.args[0])
        result = close_trade_manual(trade_id, user_id)
        emoji = "🟢" if result["pnl_usdt"] >= 0 else "🔴"
        await update.message.reply_text(
            f"{emoji} Position `{result['symbol']}` fermée. "
            f"PnL : {result['pnl_usdt']:.2f} USDT ({result['pnl_pct']:.2f}%)",
            parse_mode=ParseMode.MARKDOWN,
        )
    except (ValueError, BinanceClientError) as e:
        await update.message.reply_text(f"⚠️ {e}")


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(pnl_usdt), 0),
                       COALESCE(SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END), 0)
                FROM trades WHERE user_id = %s AND status = 'closed'
                """,
                (user_id,),
            )
            total, pnl_sum, wins = cur.fetchone()
    finally:
        conn.close()

    winrate = (wins / total * 100) if total else 0
    await update.message.reply_text(
        f"📊 *Statistiques de trading*\n\n"
        f"Trades clôturés : {total}\n"
        f"PnL cumulé : {pnl_sum:.2f} USDT\n"
        f"Win rate : {winrate:.1f}%",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /account (et /balance, /solde) — Visualisation complète du solde, PnL et positions Binance."""
    user_id = update.effective_user.id
    config = get_config(user_id)

    try:
        info = get_full_account_info(user_id, market_type=config.market_type)
    except Exception as e:
        logger.error("cmd_account failed for user=%s: %s", user_id, e)
        msg = (
            f"❌ Impossible de récupérer le solde Binance ({config.market_type.upper()}) :\n"
            f"{e}\n\n"
            "💡 Vérifie tes clés avec `/setapikeys` ou change de marché avec `/setmarket spot` / `/setmarket futures`."
        )
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(msg)
            except Exception:
                await update.callback_query.message.reply_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    lines = [
        f"💼 *Tableau de Bord Compte Binance ({info['market_type'].upper()})*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 *Solde Total* : `{info['total_wallet_balance']:.2f} USDT`",
        f"💵 *Montant Disponible* : `{info['available_balance']:.2f} USDT`",
        f"📊 *PnL Non Réalisé* : `{info['unrealized_pnl']:+.2f} USDT`",
    ]

    if info["market_type"] == "futures":
        lines.append(f"⚡ *Taux Marge Utilisée* : `{info['margin_used_pct']}%`")

    lines.append("\n🪙 *Détail des Actifs* :")
    if info["assets"]:
        for a in info["assets"][:8]:
            if info["market_type"] == "futures":
                lines.append(f"  • *{a['asset']}* : {a['wallet']:.4f} (Dispo: {a.get('available', 0):.2f} | PnL: {a.get('unrealized_pnl', 0):+.2f})")
            else:
                lines.append(f"  • *{a['asset']}* : {a['total']:.4f} (~{a.get('usdt_value', 0):.2f} USDT)")
    else:
        lines.append("  • Aucun actif actif.")

    lines.append("\n📈 *Positions Ouvertes Binance* :")
    if info["positions"]:
        for p in info["positions"]:
            lines.append(
                f"  • *{p['symbol']}* ({p['side']} x{p['leverage']})\n"
                f"    Qty: {p['quantity']} | Entrée: {p['entry_price']:.4f} | Prix: {p['mark_price']:.4f}\n"
                f"    PnL: `{p['unrealized_pnl']:+.2f} USDT` | Liq: {p['liquidation_price']:.4f}"
            )
    else:
        lines.append("  • Aucune position ouverte sur Binance.")

    if info.get("recent_trades"):
        lines.append(f"\n💸 *Commissions Récentes* : `{info['total_commissions']:.4f} USDT`")

    keyboard = [
        [
            InlineKeyboardButton("🔄 Rafraîchir", callback_data="cmd_account"),
            InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_back"),
        ]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    full_text = "\n".join(lines)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(full_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            plain = full_text.replace("*", "").replace("`", "")
            await update.callback_query.message.reply_text(plain, reply_markup=markup)
    else:
        try:
            await update.message.reply_text(full_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            plain = full_text.replace("*", "").replace("`", "")
            await update.message.reply_text(plain, reply_markup=markup)


async def cmd_trade_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, direction, pnl_usdt, exit_reason, closed_at
                FROM trades WHERE user_id = %s AND status = 'closed'
                ORDER BY closed_at DESC LIMIT 10
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        await update.message.reply_text("Aucun trade dans l'historique.")
        return

    lines = ["🕓 *10 derniers trades*\n"]
    for symbol, direction, pnl, reason, closed_at in rows:
        emoji = "🟢" if (pnl or 0) >= 0 else "🔴"
        lines.append(f"{emoji} `{symbol}` {direction} — {pnl:.2f} USDT ({reason})")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_setleverage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await _delete_sensitive_command_message(update, "setleverage")
    ok, msg = _sensitive_authorized(user_id, context)
    if not ok:
        await update.message.reply_text(f"🔐 {msg}")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage : /setleverage <valeur_entière> <code>")
        return
    leverage = int(context.args[0])
    if leverage < 1 or leverage > 125:
        await update.message.reply_text("Le levier doit être entre 1 et 125.")
        return
    update_config(user_id, leverage=leverage)
    await update.message.reply_text(f"Levier mis à jour : x{leverage}")


async def cmd_setrisk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await _delete_sensitive_command_message(update, "setrisk")
    ok, msg = _sensitive_authorized(user_id, context)
    if not ok:
        await update.message.reply_text(f"🔐 {msg}")
        return
    if not context.args:
        await update.message.reply_text("Usage : /setrisk <pourcentage> <code>")
        return
    try:
        risk = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Valeur invalide.")
        return
    if risk <= 0 or risk > 20:
        await update.message.reply_text("Le risque par trade doit être entre 0 et 20%.")
        return
    update_config(user_id, risk_per_trade=risk)
    await update.message.reply_text(f"Risque par trade mis à jour : {risk}%")


async def cmd_setmaxpos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage : /setmaxpos <1-10>")
        return
    max_positions = int(context.args[0])
    if max_positions < 1 or max_positions > 10:
        await update.message.reply_text("Le nombre maximal de positions doit être entre 1 et 10.")
        return
    update_config(user_id, max_positions=max_positions)
    await update.message.reply_text(f"Max positions mis à jour : {max_positions}")


async def cmd_setminscore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage : /setminscore <0-100>")
        return
    min_score = int(context.args[0])
    if min_score < 0 or min_score > 100:
        await update.message.reply_text("Le score minimum doit être entre 0 et 100.")
        return
    update_config(user_id, min_score=min_score)
    await update.message.reply_text(f"Score minimum mis à jour : {min_score}")


async def cmd_setdailymaxloss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /setdailymaxloss <pourcentage>")
        return
    try:
        max_daily_loss = float(context.args[0])
    except ValueError:
        await update.message.reply_text("Valeur invalide.")
        return
    if max_daily_loss <= 0 or max_daily_loss > 100:
        await update.message.reply_text("La perte maximale journalière doit être entre 0 et 100%.")
        return
    update_config(user_id, max_daily_loss=max_daily_loss)
    await update.message.reply_text(f"Perte max/jour mise à jour : {max_daily_loss}%")


async def cmd_setmarket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /setmarket <spot|futures>")
        return
    market_type = context.args[0].lower()
    if market_type not in ("spot", "futures"):
        await update.message.reply_text("Mode de marché invalide. Utilise spot ou futures.")
        return
    update_config(user_id, market_type=market_type)
    await update.message.reply_text(f"Marché AutoTrade mis à jour : {market_type}")


async def cmd_settradingstyle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /settradingstyle <scalping|scalping_15m|day|swing|position>")
        return
    style = context.args[0].lower()
    if style not in ("scalping", "scalping_15m", "day", "swing", "position"):
        await update.message.reply_text("Style de trading invalide.")
        return
    fields = {"trading_style": style}
    if style == "scalping":
        fields["analysis_timeframe"] = "5m"
    elif style == "scalping_15m":
        fields["analysis_timeframe"] = "15m"
    update_config(user_id, **fields)
    await update.message.reply_text(f"Style AutoTrade mis à jour : {style}")


async def cmd_setanalysistf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /setanalysistf <5m|15m|1h|4h|1d>")
        return
    timeframe = context.args[0].lower()
    if timeframe not in ("5m", "15m", "1h", "4h", "1d"):
        await update.message.reply_text("Timeframe invalide.")
        return
    update_config(user_id, analysis_timeframe=timeframe)
    await update.message.reply_text(f"Timeframe d'analyse AutoTrade mis à jour : {timeframe}")


async def cmd_setanalysisinterval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage : /setanalysisinterval <5|10>")
        return
    interval = int(context.args[0])
    if interval not in (5, 10):
        await update.message.reply_text("Intervalle invalide. Utilise 5 ou 10 minutes.")
        return
    update_config(user_id, analysis_interval_minutes=interval)
    await update.message.reply_text(f"Intervalle d'analyse mis à jour : {interval} minutes")


async def cmd_settrailing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /settrailing <on|off> [1-20] ou /settrailing pct <1-20>")
        return
    action = context.args[0].lower()
    fields = {}
    state = _parse_on_off(action)
    if state is None and action != "pct":
        await update.message.reply_text("Usage : /settrailing <on|off> [1-20] ou /settrailing pct <1-20>")
        return
    if action == "pct":
        if len(context.args) < 2:
            await update.message.reply_text("Usage : /settrailing pct <1-20>")
            return
        pct_arg = context.args[1]
    else:
        fields["trailing_stop"] = state
        pct_arg = context.args[1] if len(context.args) >= 2 else None
    if pct_arg is not None:
        try:
            pct = float(pct_arg)
        except ValueError:
            await update.message.reply_text("Distance trailing invalide.")
            return
        if pct <= 0 or pct > 20:
            await update.message.reply_text("La distance trailing doit être entre 0 et 20%.")
            return
        fields["trailing_stop_pct"] = pct
    update_config(user_id, **fields)
    config = get_config(user_id)
    await update.message.reply_text(f"Trailing stop mis à jour : {'ON' if config.trailing_stop else 'OFF'} ({config.trailing_stop_pct}%)")


async def cmd_setcooldown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage : /setcooldown <secondes 0-86400>")
        return
    cooldown = int(context.args[0])
    if cooldown < 0 or cooldown > 86400:
        await update.message.reply_text("Le cooldown doit être entre 0 et 86400 secondes.")
        return
    update_config(user_id, cooldown_seconds=cooldown)
    await update.message.reply_text(f"Cooldown mis à jour : {cooldown} secondes")


async def cmd_settestnet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /settestnet <on|off>")
        return
    state = _parse_on_off(context.args[0])
    if state is None:
        await update.message.reply_text("Valeur invalide. Utilise on ou off.")
        return
    update_config(user_id, testnet=state)
    await update.message.reply_text(f"Testnet mis à jour : {'ON' if state else 'OFF — argent réel'}")


async def cmd_setdca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /setdca <off|on> [steps 1-10] [step_pct 0.1-20]")
        return
    state = _parse_on_off(context.args[0])
    if state is None:
        await update.message.reply_text("Usage : /setdca <off|on> [steps 1-10] [step_pct 0.1-20]")
        return
    fields = {"dca_enabled": state}
    if len(context.args) >= 2:
        try:
            steps = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Nombre d'étapes DCA invalide.")
            return
        if steps < 1 or steps > 10:
            await update.message.reply_text("Les étapes DCA doivent être entre 1 et 10.")
            return
        fields["dca_steps"] = steps
    if len(context.args) >= 3:
        try:
            step_pct = float(context.args[2])
        except ValueError:
            await update.message.reply_text("Pourcentage d'étape DCA invalide.")
            return
        if step_pct < 0.1 or step_pct > 20:
            await update.message.reply_text("Le pourcentage d'étape DCA doit être entre 0.1 et 20%.")
            return
        fields["dca_step_pct"] = step_pct
    update_config(user_id, **fields)
    cfg = get_config(user_id)
    await update.message.reply_text(f"DCA mis à jour : {'ON' if cfg.dca_enabled else 'OFF'} ({cfg.dca_steps} étapes, {cfg.dca_step_pct}%)")


async def cmd_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /whitelist <add|remove|clear> <SYMBOLE>")
        return
    action = context.args[0].lower()
    config = get_config(user_id)
    wl = list(config.symbol_whitelist)
    if action == "clear":
        update_config(user_id, symbol_whitelist=[])
        await update.message.reply_text("Whitelist vidée.")
        return
    if action not in ("add", "remove") or len(context.args) < 2:
        await update.message.reply_text("Usage : /whitelist <add|remove|clear> <SYMBOLE>")
        return
    try:
        symbol = normalize_symbol(context.args[1])
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    if action == "add" and symbol not in wl:
        wl.append(symbol)
    if action == "remove":
        wl = [s for s in wl if s != symbol]
    update_config(user_id, symbol_whitelist=wl)
    await update.message.reply_text(f"Whitelist mise à jour : {', '.join(wl) or '—'}")


async def cmd_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Usage : /blacklist <add|remove|clear> <SYMBOLE>")
        return
    action = context.args[0].lower()
    config = get_config(user_id)
    bl = list(config.symbol_blacklist)
    if action == "clear":
        update_config(user_id, symbol_blacklist=[])
        await update.message.reply_text("Blacklist vidée.")
        return
    if action not in ("add", "remove") or len(context.args) < 2:
        await update.message.reply_text("Usage : /blacklist <add|remove|clear> <SYMBOLE>")
        return
    try:
        symbol = normalize_symbol(context.args[1])
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return
    if action == "add" and symbol not in bl:
        bl.append(symbol)
    if action == "remove":
        bl = [s for s in bl if s != symbol]
    update_config(user_id, symbol_blacklist=bl)
    await update.message.reply_text(f"Blacklist mise à jour : {', '.join(bl) or '—'}")


async def cmd_emergency_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text("🛑 Fermeture de toutes les positions en cours...")
    closed = emergency_stop_all(user_id)
    await update.message.reply_text(
        f"✅ {closed} position(s) fermée(s). Mode automatique désactivé."
    )


# ---------------------------------------------------------------------------
# Menu principal (boutons)
# ---------------------------------------------------------------------------

def build_autotrade_menu_buttons() -> list:
    """À insérer dans build_main_menu() du bot existant."""
    return [
        [InlineKeyboardButton("📊 AutoTrade", callback_data="menu_autotrade")],
        [InlineKeyboardButton("📈 Positions", callback_data="menu_positions")],
        [InlineKeyboardButton("⚙️ Trading Config", callback_data="menu_trading_config")],
    ]


def _build_autotrade_menu(user_id: int):
    """Construit (texte, clavier) du menu AutoTrade. Réutilisé par /autotrade et le callback menu_autotrade."""
    config = get_config(user_id)
    status = "ON ✅" if config.auto_trade else "OFF ❌"
    
    market = escape_markdown(config.market_type.upper())
    tf = escape_markdown(config.analysis_timeframe)
    interval = escape_markdown(str(config.analysis_interval_minutes))
    style = escape_markdown(config.trading_style)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Basculer (actuellement {status})", callback_data="toggle_autotrade")],
        [InlineKeyboardButton("Mode spot/futures", callback_data="menu_market_mode")],
        [InlineKeyboardButton("Analyse periodique", callback_data="menu_analysis_config")],
        [InlineKeyboardButton("⚙️ Configuration", callback_data="menu_trading_config")],
        [InlineKeyboardButton("📈 Positions", callback_data="menu_positions")],
        [InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_back")],
    ])
    text = (
        f"🤖 *AutoTrade Binance*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Mode automatique : *{status}*\n"
        f"Marché : *{market}*\n"
        f"Analyse : *{tf} / {interval} min*\n"
        f"Style : *{style}*\n\n"
        f"Commandes protégées : {escape_markdown('/periodic_analysis')} on|off, {escape_markdown('/setanalysisinterval')}, {escape_markdown('/setanalysistf')}, {escape_markdown('/settradingstyle')}."
    )
    return text, keyboard


async def trading_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "menu_autotrade":
        text, keyboard = _build_autotrade_menu(user_id)
        await _safe_edit(query, text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    elif data == "toggle_autotrade":
        config = get_config(user_id)
        if config.auto_trade:
            update_config(user_id, auto_trade=False)
        else:
            await _safe_edit(
                query,
                "🔐 Activation AutoTrade refusée depuis un bouton non authentifié.\n"
                "Utilise une commande protégée avec code de sécurité avant d'activer le trading réel.",
            )
            return
        query.data = "menu_autotrade"
        await trading_callback_router(update, context)

    elif data == "menu_market_mode":
        config = get_config(user_id)
        spot_label = "🟢 Spot (Actif)" if config.market_type == "spot" else "Spot"
        futures_label = "🟢 Futures (Actif)" if config.market_type == "futures" else "Futures"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(spot_label, callback_data="set_market_spot"),
                InlineKeyboardButton(futures_label, callback_data="set_market_futures"),
            ],
            [
                InlineKeyboardButton("⬅️ Retour AutoTrade", callback_data="menu_autotrade"),
                InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_back"),
            ],
        ])
        await _safe_edit(
            query,
            f"🎯 *Mode de Marché Actuel :* `{escape_markdown(config.market_type.upper())}`\n\n"
            f"Choisis le mode à utiliser pour les analyses et la prise d'ordres. Commande protégée : /setmarket <spot|futures> <code>.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data.startswith("set_market_"):
        new_market = data.replace("set_market_", "").strip().lower()
        if new_market in ("spot", "futures"):
            update_config(user_id, market_type=new_market)
        query.data = "menu_market_mode"
        await trading_callback_router(update, context)
        return

    elif data == "menu_analysis_config":
        config = get_config(user_id)
        p_status = "ACTIVÉE ✅" if config.periodic_analysis_enabled else "DÉSACTIVÉE ❌"
        toggle_btn_label = "🔴 Désactiver l'Analyse Périodique" if config.periodic_analysis_enabled else "🟢 Activer l'Analyse Périodique"

        cur_int = int(config.analysis_interval_minutes or 5)
        cur_tf = str(config.analysis_timeframe or "5m")
        cur_style = str(config.trading_style or "scalping")

        from execution_engine import _resolve_requested_scan_symbols
        req_symbols, req_source = _resolve_requested_scan_symbols(user_id, config)
        req_symbols_str = escape_markdown(", ".join(req_symbols))
        req_source_str = escape_markdown(req_source)

        interval = escape_markdown(str(cur_int))
        tf = escape_markdown(cur_tf)
        style = escape_markdown(cur_style)

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(toggle_btn_label, callback_data="toggle_periodic_analysis"),
            ],
            [
                InlineKeyboardButton("🚀 Lancer une analyse maintenant", callback_data="run_periodic_analysis_now"),
            ],
            [
                InlineKeyboardButton(f"{'🟢 ' if cur_int == 5 else ''}⏱ 5 min", callback_data="set_analysis_interval_5"),
                InlineKeyboardButton(f"{'🟢 ' if cur_int == 10 else ''}⏱ 10 min", callback_data="set_analysis_interval_10"),
            ],
            [
                InlineKeyboardButton(f"{'🟢 ' if cur_tf == '5m' else ''}5m", callback_data="set_analysis_tf_5m"),
                InlineKeyboardButton(f"{'🟢 ' if cur_tf == '15m' else ''}15m", callback_data="set_analysis_tf_15m"),
                InlineKeyboardButton(f"{'🟢 ' if cur_tf == '1h' else ''}1h", callback_data="set_analysis_tf_1h"),
                InlineKeyboardButton(f"{'🟢 ' if cur_tf == '4h' else ''}4h", callback_data="set_analysis_tf_4h"),
                InlineKeyboardButton(f"{'🟢 ' if cur_tf == '1d' else ''}1d", callback_data="set_analysis_tf_1d"),
            ],
            [
                InlineKeyboardButton(f"{'🟢 ' if cur_style == 'scalping' else ''}Scalping 5m", callback_data="set_analysis_style_scalping"),
                InlineKeyboardButton(f"{'🟢 ' if cur_style == 'scalping_15m' else ''}Scalping 15m", callback_data="set_analysis_style_scalping_15m"),
            ],
            [
                InlineKeyboardButton(f"{'🟢 ' if cur_style == 'day' else ''}Day", callback_data="set_analysis_style_day"),
                InlineKeyboardButton(f"{'🟢 ' if cur_style == 'swing' else ''}Swing", callback_data="set_analysis_style_swing"),
                InlineKeyboardButton(f"{'🟢 ' if cur_style == 'position' else ''}Position", callback_data="set_analysis_style_position"),
            ],
            [
                InlineKeyboardButton("⭐ Gérer ma Watchlist", callback_data="menu_watchlist"),
                InlineKeyboardButton("✅ Gérer ma Whitelist", callback_data="menu_whitelist"),
            ],
            [
                InlineKeyboardButton("⬅️ Retour AutoTrade", callback_data="menu_autotrade"),
                InlineKeyboardButton("⬅️ Retour Analyse", callback_data="menu_analyse"),
            ],
            [
                InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_back"),
            ],
        ])
        await _safe_edit(
            query,
            f"📊 *Configuration Analyse Périodique*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"• État automatique : *{p_status}*\n"
            f"• Fréquence du scan : *toutes les {interval} min*\n"
            f"• Timeframe bougies : *{tf}*\n"
            f"• Style de stratégie : *{style}*\n"
            f"• Score minimum exigé : *{config.min_score}/100*\n"
            f"• Symboles ciblés ({req_source_str}) : `{req_symbols_str}`\n\n"
            f"💡 _Seuls les symboles documentés dans le bot (`BTCUSDT`, `ETHUSDT`, `BTCUSD`, `ETHUSD`, `XAUUSD`) sont analysés._",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "toggle_periodic_analysis":
        config = get_config(user_id)
        new_state = not config.periodic_analysis_enabled
        update_config(user_id, periodic_analysis_enabled=new_state)
        query.data = "menu_analysis_config"
        await trading_callback_router(update, context)

    elif data == "run_periodic_analysis_now":
        config = get_config(user_id)
        await _safe_edit(
            query,
            f"⏳ *Analyse périodique en cours...*\n\n"
            f"Scan des paires principales et de ta Watchlist en `{escape_markdown(config.analysis_timeframe)}` (style `{escape_markdown(config.trading_style)}`)...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Retour Configuration", callback_data="menu_analysis_config")]]),
            parse_mode=ParseMode.MARKDOWN,
        )
        from execution_engine import run_market_analysis_for_user
        report = await run_market_analysis_for_user(context, user_id, int(config.analysis_interval_minutes or 5), send_telegram=False)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Relancer l'analyse maintenant", callback_data="run_periodic_analysis_now")],
            [InlineKeyboardButton("⚙️ Configuration Analyse Périodique", callback_data="menu_analysis_config")],
            [InlineKeyboardButton("⬅️ Retour Analyse", callback_data="menu_analyse"), InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_back")],
        ])
        try:
            await _safe_edit(query, report, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            plain = report.replace("*", "").replace("`", "").replace("_", "")
            await _safe_edit(query, plain, reply_markup=kb)

    elif data.startswith("set_analysis_interval_"):
        try:
            interval = int(data.replace("set_analysis_interval_", ""))
            if interval in (5, 10):
                update_config(user_id, analysis_interval_minutes=interval)
        except ValueError:
            pass
        query.data = "menu_analysis_config"
        await trading_callback_router(update, context)

    elif data.startswith("set_analysis_tf_"):
        timeframe = data.replace("set_analysis_tf_", "")
        if timeframe in ("5m", "15m", "1h", "4h", "1d"):
            update_config(user_id, analysis_timeframe=timeframe)
            from user_manager import UserManager
            UserManager.get_instance().set_setting(user_id, "timeframe", timeframe)
        query.data = "menu_analysis_config"
        await trading_callback_router(update, context)

    elif data.startswith("set_analysis_style_"):
        style = data.replace("set_analysis_style_", "")
        if style in ("scalping", "scalping_15m", "day", "swing", "position"):
            fields = {"trading_style": style}
            if style == "scalping":
                fields["analysis_timeframe"] = "5m"
            elif style == "scalping_15m":
                fields["analysis_timeframe"] = "15m"
            update_config(user_id, **fields)
            from user_manager import UserManager
            UserManager.get_instance().set_setting(user_id, "trading_style", style)
            if "analysis_timeframe" in fields:
                UserManager.get_instance().set_setting(user_id, "timeframe", fields["analysis_timeframe"])
        query.data = "menu_analysis_config"
        await trading_callback_router(update, context)

    elif data == "menu_positions":
        trades = get_open_trades(user_id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Rafraîchir", callback_data="menu_positions")],
            [InlineKeyboardButton("⬅️ Retour AutoTrade", callback_data="menu_autotrade"), InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_back")]
        ])
        if not trades:
            await query.edit_message_text("📈 *Positions ouvertes :*\n\nAucune position ouverte actuellement.", reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            return
        lines = [f"#{t['id']} {escape_markdown(t['symbol'])} {t['direction']} qty={t['quantity']} (SL {t['sl_price']} / TP {t['tp_price']})" for t in trades]
        await query.edit_message_text("📈 *Positions ouvertes :*\n\n" + "\n".join(lines), reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    elif data == "menu_trading_config":
        config = get_config(user_id)
        trailing_str = f"{'ON' if config.trailing_stop else 'OFF'} ({config.trailing_stop_pct}%)"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"⚡ Levier (x{config.leverage})", callback_data="menu_leverage"),
                InlineKeyboardButton(f"📊 Risque ({config.risk_per_trade}%)", callback_data="menu_risk"),
            ],
            [
                InlineKeyboardButton(f"🎯 Max positions ({config.max_positions})", callback_data="menu_maxpos"),
                InlineKeyboardButton(f"🧠 Score min ({config.min_score})", callback_data="menu_minscore"),
            ],
            [InlineKeyboardButton(f"📉 Trailing stop ({trailing_str})", callback_data="menu_trailing")],
            [
                InlineKeyboardButton("✅ Whitelist", callback_data="menu_whitelist"),
                InlineKeyboardButton("🚫 Blacklist", callback_data="menu_blacklist"),
            ],
            [
                InlineKeyboardButton("💰 PnL", callback_data="menu_pnl"),
                InlineKeyboardButton("🕓 Historique", callback_data="menu_history_trades"),
            ],
            [InlineKeyboardButton("🔐 Code PIN de Sécurité (/setsecurity)", callback_data="cmd_setsecurity")],
            [InlineKeyboardButton("⬅️ Retour AutoTrade", callback_data="menu_autotrade"), InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_back")]
        ])
        await query.edit_message_text(
            f"⚙️ *Trading Config*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Levier : x{config.leverage}\n"
            f"Risque/trade : {config.risk_per_trade}%\n"
            f"Marché : {config.market_type}\n"
            f"Analyse : {config.analysis_timeframe}/{config.analysis_interval_minutes}m\n"
            f"Style : {config.trading_style}\n"
            f"Max positions : {config.max_positions}\n"
            f"Score minimum : {config.min_score}\n"
            f"Trailing stop : {trailing_str}"
            f"{' — déplacement auto futures non disponible' if config.market_type == 'futures' else ''}\n"
            f"DCA : {'configuré mais non disponible' if config.dca_enabled else 'OFF'} ({config.dca_steps} étapes, {config.dca_step_pct}%)\n"
            f"Cooldown : {config.cooldown_seconds}s\n"
            f"Testnet : {'OUI' if config.testnet else 'NON — argent réel'}\n\n"
            f"Utilise les boutons ci-dessous pour modifier directement vos réglages.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )

    elif data == "menu_leverage":
        config = get_config(user_id)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("x1", callback_data="set_leverage_1"),
                InlineKeyboardButton("x2", callback_data="set_leverage_2"),
                InlineKeyboardButton("x5", callback_data="set_leverage_5"),
            ],
            [
                InlineKeyboardButton("x10", callback_data="set_leverage_10"),
                InlineKeyboardButton("x20", callback_data="set_leverage_20"),
                InlineKeyboardButton("x50", callback_data="set_leverage_50"),
            ],
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        await query.edit_message_text(
            f"⚡ *Levier actuel : x{config.leverage}*\n\nChoisis une nouvelle valeur (ou /setleverage <n> pour une valeur précise, jusqu'à x125).",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data.startswith("set_leverage_"):
        try:
            lev = int(data.replace("set_leverage_", ""))
            if 1 <= lev <= 125:
                update_config(user_id, leverage=lev)
        except ValueError:
            pass
        query.data = "menu_trading_config"
        await trading_callback_router(update, context)

    elif data == "menu_risk":
        config = get_config(user_id)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1%", callback_data="set_risk_1"),
                InlineKeyboardButton("2%", callback_data="set_risk_2"),
                InlineKeyboardButton("5%", callback_data="set_risk_5"),
                InlineKeyboardButton("10%", callback_data="set_risk_10"),
            ],
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        await query.edit_message_text(
            f"📊 *Risque par trade actuel : {config.risk_per_trade}%*\n\nChoisis une nouvelle valeur (ou /setrisk <pourcentage> pour une valeur précise, jusqu'à 20%).",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data.startswith("set_risk_"):
        try:
            r = float(data.replace("set_risk_", ""))
            if 0 < r <= 20:
                update_config(user_id, risk_per_trade=r)
        except ValueError:
            pass
        query.data = "menu_trading_config"
        await trading_callback_router(update, context)

    elif data == "menu_maxpos":
        config = get_config(user_id)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1", callback_data="set_maxpos_1"),
                InlineKeyboardButton("3", callback_data="set_maxpos_3"),
                InlineKeyboardButton("5", callback_data="set_maxpos_5"),
                InlineKeyboardButton("10", callback_data="set_maxpos_10"),
            ],
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        await query.edit_message_text(
            f"🎯 *Max positions simultanées actuel : {config.max_positions}*\n\nChoisis une nouvelle valeur ou utilise /setmaxpos <1-10>.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data.startswith("set_maxpos_"):
        try:
            m = int(data.replace("set_maxpos_", ""))
            if 1 <= m <= 10:
                update_config(user_id, max_positions=m)
        except ValueError:
            pass
        query.data = "menu_trading_config"
        await trading_callback_router(update, context)

    elif data == "menu_minscore":
        config = get_config(user_id)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("75", callback_data="set_minscore_75"),
                InlineKeyboardButton("78 (Recommandé)", callback_data="set_minscore_78"),
                InlineKeyboardButton("82", callback_data="set_minscore_82"),
                InlineKeyboardButton("85", callback_data="set_minscore_85"),
            ],
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        await _safe_edit(
            query,
            f"🧠 *Score minimum actuel pour exécuter un signal : {config.min_score}/100*\n\nChoisis un seuil haute sélectivité (78 recommandé pour gagner plus et perdre moins) ou utilise /setminscore <70-100>.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data.startswith("set_minscore_"):
        try:
            sc = int(data.replace("set_minscore_", ""))
            if 0 <= sc <= 100:
                update_config(user_id, min_score=sc)
        except ValueError:
            pass
        query.data = "menu_trading_config"
        await trading_callback_router(update, context)

    elif data == "menu_trailing":
        config = get_config(user_id)
        t_status = "ACTIVÉ ✅" if config.trailing_stop else "DÉSACTIVÉ ❌"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Trailing stop ({t_status})", callback_data="toggle_trailing")],
            [
                InlineKeyboardButton("1%", callback_data="set_trailing_1"),
                InlineKeyboardButton("2%", callback_data="set_trailing_2"),
                InlineKeyboardButton("3%", callback_data="set_trailing_3"),
                InlineKeyboardButton("5%", callback_data="set_trailing_5"),
            ],
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        await query.edit_message_text(
            f"📉 *Trailing Stop*\n\nÉtat : *{t_status}*\nDistance actuelle : *{config.trailing_stop_pct}%*\n"
            f"Utilise /settrailing <on|off> [pct] ou /settrailing pct <pct>.\n"
            f"Note : le déplacement automatique d’ordre stop futures n’est pas disponible.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "toggle_trailing":
        config = get_config(user_id)
        update_config(user_id, trailing_stop=not config.trailing_stop)
        query.data = "menu_trading_config"
        await trading_callback_router(update, context)

    elif data.startswith("set_trailing_"):
        try:
            pct = float(data.replace("set_trailing_", ""))
            if 0.1 <= pct <= 20:
                update_config(user_id, trailing_stop_pct=pct, trailing_stop=True)
        except ValueError:
            pass
        query.data = "menu_trading_config"
        await trading_callback_router(update, context)

    elif data == "menu_whitelist":
        config = get_config(user_id)
        wl = ", ".join(config.symbol_whitelist) or "— (aucune restriction)"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        await query.edit_message_text(
            f"✅ *Whitelist AutoTrade*\n\n{wl}\n\n"
            f"Utilise /whitelist <add|remove|clear> <SYMBOLE> <code>.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "menu_blacklist":
        config = get_config(user_id)
        bl = ", ".join(config.symbol_blacklist) or "— (aucune)"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        await query.edit_message_text(
            f"🚫 *Blacklist AutoTrade*\n\n{bl}\n\n"
            f"Utilise /blacklist <add|remove|clear> <SYMBOLE> <code>.",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "menu_pnl":
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*), COALESCE(SUM(pnl_usdt), 0),
                           COALESCE(SUM(CASE WHEN pnl_usdt > 0 THEN 1 ELSE 0 END), 0)
                    FROM trades WHERE user_id = %s AND status = 'closed'
                    """,
                    (user_id,),
                )
                total, pnl_sum, wins = cur.fetchone()
        finally:
            conn.close()
        winrate = (wins / total * 100) if total else 0
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Rafraîchir", callback_data="menu_pnl")],
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        await query.edit_message_text(
            f"📊 *Statistiques de trading*\n\n"
            f"Trades clôturés : {total}\n"
            f"PnL cumulé : {pnl_sum:.2f} USDT\n"
            f"Win rate : {winrate:.1f}%",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )

    elif data == "menu_history_trades":
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT symbol, direction, pnl_usdt, exit_reason, closed_at
                    FROM trades WHERE user_id = %s AND status = 'closed'
                    ORDER BY closed_at DESC LIMIT 10
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Retour Config", callback_data="menu_trading_config")],
        ])
        if not rows:
            await query.edit_message_text("Aucun trade dans l'historique.", reply_markup=keyboard)
            return
        lines = ["🕓 *10 derniers trades*\n"]
        for symbol, direction, pnl, reason, closed_at in rows:
            emoji = "🟢" if (pnl or 0) >= 0 else "🔴"
            lines.append(f"{emoji} `{escape_markdown(symbol)}` {direction} — {pnl:.2f} USDT ({reason})")
        await query.edit_message_text("\n".join(lines), reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("manual_trade_cancel_"):
        token = data.replace("manual_trade_cancel_", "")
        context.user_data.get("manual_trade_confirmations", {}).pop(token, None)
        await query.edit_message_caption(caption="Analyse annulée. Aucun trade ouvert.")

    elif data.startswith("manual_trade_execute_"):
        token = data.replace("manual_trade_execute_", "")
        signal = context.user_data.get("manual_trade_confirmations", {}).pop(token, None)
        if not signal or int(signal.get("user_id")) != int(user_id):
            await query.edit_message_caption(caption="Confirmation expirée ou invalide.")
            return
        signal["id"] = f"manual-{token}"
        config = get_config(user_id)
        allowed, reason = validate_signal_for_execution(user_id, signal, config)
        if not allowed:
            await query.edit_message_caption(caption=f"❌ Ouverture refusée : {reason}")
            return
        trade = execute_signal(signal, config, execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED)
        if trade["status"] == "open":
            await query.edit_message_caption(caption=f"✅ Position ouverte : {trade['symbol']} {trade['direction']} qty={trade['quantity']}")
        else:
            await query.edit_message_caption(caption=f"⚠️ Échec d'ouverture : {trade.get('error_message')}")

    elif data.startswith("trading_open_"):
        signal_id = data.replace("trading_open_", "")
        await _confirm_open_signal(query, context, signal_id)

    elif data.startswith("trading_reject_"):
        signal_id = data.replace("trading_reject_", "")
        if not _signal_belongs_to_user(signal_id, user_id):
            await query.edit_message_text("❌ Ce signal ne t'appartient pas.")
            return
        mark_signal_status(signal_id, "rejected")
        await query.edit_message_text("❌ Signal refusé.")

    elif data.startswith("trading_edit_"):
        signal_id = data.replace("trading_edit_", "")
        await query.edit_message_text(
            f"Pour modifier SL/TP du signal {signal_id}, réponds avec :\n"
            f"/editsignal {signal_id} <nouveau_sl> <nouveau_tp>"
        )



async def cmd_confirmmanual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await context.bot.send_message(chat_id=user_id, text="Usage : /confirmmanual <token>")
        return
    token = context.args[0]
    signal = context.user_data.get("manual_trade_confirmations", {}).pop(token, None)
    if not signal or int(signal.get("user_id")) != int(user_id):
        await context.bot.send_message(chat_id=user_id, text="Confirmation expirée ou invalide.")
        return
    signal["id"] = f"manual-{token}"
    config = get_config(user_id)
    allowed, reason = validate_signal_for_execution(user_id, signal, config)
    if not allowed:
        await context.bot.send_message(chat_id=user_id, text=f"❌ Ouverture refusée : {reason}")
        return
    trade = execute_signal(signal, config, execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED)
    if trade["status"] == "open":
        await context.bot.send_message(chat_id=user_id, text=f"✅ Position ouverte : {trade['symbol']} {trade['direction']} qty={trade['quantity']}")
    else:
        await context.bot.send_message(chat_id=user_id, text=f"⚠️ Échec d'ouverture : {trade.get('error_message')}")


def _signal_belongs_to_user(signal_id: str, user_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM signals WHERE id = %s", (signal_id,))
            row = cur.fetchone()
            return bool(row and int(row[0]) == int(user_id))
    finally:
        conn.close()


def _sl_tp_are_coherent(direction: str, entry_price: float | None, sl: float, tp: float) -> bool:
    if entry_price is None:
        return True
    if direction == "BUY":
        return sl < entry_price < tp
    if direction == "SELL":
        return tp < entry_price < sl
    return False

async def cmd_editsignal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage : /editsignal <id_signal> <nouveau_sl> <nouveau_tp>

    Permet de modifier le SL/TP d'un signal en attente de confirmation
    (déclenché par le bouton "✏️ Modifier SL/TP" en mode semi-automatique)
    avant de l'ouvrir avec trading_open_<id> ou de le refuser.
    """
    user_id = update.effective_user.id

    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage : /editsignal <id_signal> <nouveau_sl> <nouveau_tp>\n"
            "Exemple : /editsignal 42 1.0850 1.0920"
        )
        return

    signal_id = context.args[0]
    try:
        new_sl = float(context.args[1])
        new_tp = float(context.args[2])
    except ValueError:
        await update.message.reply_text("❌ SL et TP doivent être des nombres (ex: /editsignal 42 1.0850 1.0920).")
        return

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, symbol, direction, entry_price, status FROM signals WHERE id = %s",
                (signal_id,),
            )
            row = cur.fetchone()
            if not row:
                await update.message.reply_text("Signal introuvable (peut-être déjà expiré).")
                return

            sig_id, sig_user_id, symbol, direction, entry_price, status = row
            if int(sig_user_id) != int(user_id):
                await update.message.reply_text("❌ Ce signal ne t'appartient pas.")
                return
            if status != "awaiting_confirmation":
                await update.message.reply_text("❌ Ce signal n'est plus en attente de confirmation.")
                return
            if not _sl_tp_are_coherent(direction, entry_price, new_sl, new_tp):
                await update.message.reply_text("❌ SL/TP incohérents avec le sens du signal et le prix d'entrée.")
                return

            cur.execute(
                "UPDATE signals SET sl = %s, tp = %s WHERE id = %s",
                (new_sl, new_tp, signal_id),
            )
        conn.commit()
    finally:
        conn.close()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Ouvrir", callback_data=f"trading_open_{signal_id}"),
         InlineKeyboardButton("❌ Refuser", callback_data=f"trading_reject_{signal_id}")]
    ])
    await update.message.reply_text(
        f"✏️ Signal #{signal_id} mis à jour : {symbol} {direction}\n"
        f"Nouveau SL : {new_sl}\n"
        f"Nouveau TP : {new_tp}",
        reply_markup=keyboard,
    )


async def _confirm_open_signal(query, context: ContextTypes.DEFAULT_TYPE, signal_id: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, user_id, symbol, direction, entry_price, sl, tp, score, status, created_at "
                "FROM signals WHERE id = %s",
                (signal_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        await query.edit_message_text("Signal introuvable (peut-être déjà expiré).")
        return

    cols = ["id", "user_id", "symbol", "direction", "entry_price", "sl", "tp", "score", "status", "created_at"]
    signal = dict(zip(cols, row))
    if int(signal["user_id"]) != int(query.from_user.id):
        await query.edit_message_text("❌ Ce signal ne t'appartient pas.")
        return
    if signal["status"] != "awaiting_confirmation":
        await query.edit_message_text("❌ Ce signal n'est plus en attente de confirmation.")
        return

    config = get_config(signal["user_id"])
    allowed, reason = validate_signal_for_execution(query.from_user.id, signal, config)
    if not allowed:
        mark_signal_status(signal_id, "skipped")
        await query.edit_message_text(f"❌ Ouverture refusée : {reason}")
        return

    trade = execute_signal(signal, config, execution_context=ORDER_CONTEXT_MANUAL_AUTHENTICATED)
    if trade["status"] == "open":
        await query.edit_message_text(
            f"✅ Position ouverte : {trade['symbol']} {trade['direction']} qty={trade['quantity']}"
        )
    else:
        await query.edit_message_text(f"⚠️ Échec d'ouverture : {trade.get('error_message')}")
