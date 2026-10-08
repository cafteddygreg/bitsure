"""
Bitsure Teddy - Admin Handlers
Fonctions réservées à l'administrateur
"""

import logging
import io
import csv
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_ID
from data_fetcher import DataFetcher
from user_manager import UserManager
from history_manager import HistoryManager
from i18n import get_text

logger = logging.getLogger(__name__)
user_mgr = UserManager.get_instance()
history_mgr = HistoryManager.get_instance()

def get_user_lang(update: Update) -> str:
    user_id = update.effective_user.id
    return user_mgr.get_setting(user_id, "lang", "en")

def _is_admin_user(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    uname = getattr(user, "username", None)
    if uname:
        try:
            user_mgr.update_username(user.id, f"@{uname.lstrip('@')}")
        except Exception:
            pass
    return user_mgr.is_admin(user.id, uname)

def check_limit(func):
    """Version simplifiée pour admin - l'admin passe toujours"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        return await func(update, context, *args, **kwargs)
    return wrapper

# =========================================================
# STATS
# =========================================================

@check_limit
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return

    # Statistiques globales
    total_row = user_mgr.conn.execute("SELECT COUNT(*) as total FROM users").fetchone()
    total = total_row["total"] if total_row else 0
    free_row = user_mgr.conn.execute("SELECT COUNT(*) as c FROM users WHERE role='tester'").fetchone()
    free = free_row["c"] if free_row else 0
    pro_row = user_mgr.conn.execute("SELECT COUNT(*) as c FROM users WHERE role='pro'").fetchone()
    pro = pro_row["c"] if pro_row else 0
    
    # Santé & Watchdog
    from health_monitor import get_last_health_status
    hs = get_last_health_status()
    db_status = "✅ OK" if hs.get("db_ok", True) else "❌ DOWN"
    sched_status = "✅ Active" if hs.get("scheduler_running", True) else "❌ STOPPED"
    text = (
        f"📊 *Bitsure Teddy Stats*\n"
        f"🖥️ DB: {db_status} | Watchdog Scheduler: {sched_status}\n"
        f"👥 Utilisateurs : {total}\n🧪 Testeurs : {free}\n💎 PRO : {pro}\n\n"
    )
    
    # Détail par utilisateur
    users = user_mgr.conn.execute("SELECT user_id, role, username FROM users ORDER BY role, user_id").fetchall()
    for u in users:
        uid = u["user_id"]
        username = u["username"] or f"ID:{uid}"
        role = u["role"]
        
        # Compter les requêtes du jour
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")
        usage_row = user_mgr.conn.execute("SELECT count FROM usage WHERE user_id = %s AND date = %s", (uid, today)).fetchone()
        used = usage_row["count"] if usage_row else 0
        
        # Compter les signaux
        sig_row = user_mgr.conn.execute("SELECT COUNT(*) as c FROM signals WHERE user_id = %s", (uid,)).fetchone()
        sig_count = sig_row["c"] if sig_row else 0
        
        emoji = "💎" if role == "pro" else "🧪" if role == "tester" else "👤"
        text += f"{emoji} {uid} {username} | {role} | {used} req | {sig_count} signals\n"
    
    if len(text) > 4000:
        text = text[:4000] + "\n... (truncated)"
    
    await update.message.reply_text(text)

# =========================================================
# APPROUVER UN TESTEUR
# =========================================================

@check_limit
async def teddy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        await update.message.reply_text(
            f"⛔ Accès refusé. Ton compte (ID: `{update.effective_user.id}`, pseudo: `@{getattr(update.effective_user, 'username', '')}`) n'est pas reconnu comme admin (`@btsrteddy`).",
            parse_mode="Markdown",
        )
        return
    if not context.args:
        await update.message.reply_text(
            "Usage :\n"
            "• `/teddy <user_id ou @username>` — Approuver un utilisateur comme testeur\n"
            "• `/teddy <user_id ou @username> pro` — Activer directement l'accès PRO",
            parse_mode="Markdown",
        )
        return

    raw_target = context.args[0].strip()
    role_arg = context.args[1].lower() if len(context.args) >= 2 else None

    uid = user_mgr.resolve_user_target(raw_target, create_if_username=True)
    if uid is None:
        await update.message.reply_text(
            f"❌ Impossible de trouver `{raw_target}`.\n"
            f"💡 Passe son ID numérique (ex: `/teddy 123456789`) qu'il obtient avec `/myid`, ou son `@username`.",
            parse_mode="Markdown",
        )
        return

    existing_role = user_mgr.get_role(uid) if uid > 0 else "tester"
    if role_arg in ("pro", "paid", "premium") or existing_role == "pro" or (uid > 0 and user_mgr.has_pending_binance_payment(uid)):
        user_mgr.confirm_binance_payment(uid, force=True)
        target_label = f"`{raw_target}` (ID: `{uid}`)" if uid > 0 else f"`{raw_target}` (pré-enregistré)"
        await update.message.reply_text(f"✅ Utilisateur {target_label} activé en **PRO** (`approved=1`, `terms_accepted=1`) !", parse_mode="Markdown")
        if uid > 0:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="✅ Ton abonnement PRO Bitsure Teddy est activé ! Tape /start ou /menu pour commencer.",
                )
            except Exception as e:
                logger.error(f"[teddy] Failed to notify user {uid}: {e}")
    elif user_mgr.approve_user(uid, role="tester"):
        target_label = f"`{raw_target}` (ID: `{uid}`)" if uid > 0 else f"`{raw_target}` (pré-enregistré)"
        await update.message.reply_text(f"✅ Utilisateur {target_label} ajouté et approuvé (`approved=1`, `terms_accepted=1`) !", parse_mode="Markdown")
        if uid > 0:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="✅ Ton accès à Bitsure Teddy a été approuvé ! Tape /start ou /menu pour commencer.",
                )
            except Exception as e:
                logger.error(f"[teddy] Failed to notify user {uid}: {e}")
    else:
        await update.message.reply_text(f"❌ Utilisateur `{uid}` introuvable.", parse_mode="Markdown")

# =========================================================
# BROADCAST
# =========================================================

@check_limit
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    lang = user_mgr.get_setting(update.effective_user.id, "lang", "en")
    if not context.args:
        await update.message.reply_text(get_text(lang, "broadcast_usage"))
        return
    user_text = " ".join(context.args)
    header = "📢 *Bitsure Teddy \u2022 Announcement*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    message = header + user_text
    users = user_mgr.get_all_users()
    success = 0
    errors = []
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=message)
            success += 1
        except Exception as e:
            errors.append(str(e))
    result = f"Broadcast sent to {success}/{len(users)} users."
    if errors:
        result += f"\nErrors: {len(errors)}"
    await update.message.reply_text(result)

# =========================================================
# SWITCH API
# =========================================================

@check_limit
async def switchapi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        await update.message.reply_text("⛔ Admin only.")
        return
    fetcher = DataFetcher.get_instance()
    current = getattr(fetcher, "active_source", None) or "binance"
    failures = getattr(fetcher, "source_failures", {})
    if not context.args:
        await update.message.reply_text(
            f"🔄 Source actuelle : {current}\n"
            f"Usage : /switchapi binance|twelve|real\n"
            f"Échecs : {failures}"
        )
        return
    target = context.args[0].lower()
    if target not in ("binance", "twelve", "fcs", "real"):
        await update.message.reply_text("❌ binance, twelve ou real")
        return
    if getattr(fetcher, "ws", None):
        try:
            fetcher.ws.close()
        except Exception:
            pass
    if target == "twelve":
        fetcher._start_twelve_ws()
    else:
        fetcher.active_source = "binance" if target in ("binance", "real") else target
    await update.message.reply_text(f"✅ Switch vers {fetcher.active_source} effectué.")

# =========================================================
# FIND MEMO
# =========================================================

@check_limit
async def find_memo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /find_memo <memo>")
        return
    memo = context.args[0].upper()
    user_id = user_mgr.find_user_by_memo(memo)
    if user_id:
        await update.message.reply_text(f"✅ Mémo {memo} → User ID: {user_id}")
    else:
        await update.message.reply_text(f"❌ Aucun utilisateur trouvé pour le mémo {memo}")

# =========================================================
# CONFIRM PAYMENT
# =========================================================

@check_limit
async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        await update.message.reply_text("⛔ Commande réservée à l'administrateur (@btsrteddy).")
        return
    lang = user_mgr.get_setting(update.effective_user.id, "lang", "fr")
    if not context.args:
        await update.message.reply_text("Usage: `/confirm_payment <user_id | @username | memo>`", parse_mode="Markdown")
        return
    raw_target = context.args[0].strip()
    uid = user_mgr.resolve_user_target(raw_target, create_if_username=True)
    if uid is None:
        await update.message.reply_text("❌ Utilisateur ou mémo introuvable. Passe son `user_id` numérique ou son `@username`.", parse_mode="Markdown")
        return
    if user_mgr.confirm_binance_payment(uid, force=True):
        await update.message.reply_text(get_text(lang, "confirm_payment_ok", user_id=uid))
        if uid > 0:
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text="✅ Ton abonnement PRO Bitsure Teddy est activé ! Tape /start ou /menu pour commencer.",
                )
            except Exception as e:
                logger.error(f"[confirm_payment] Failed to notify user {uid}: {e}")
    else:
        await update.message.reply_text(get_text(lang, "confirm_payment_missing", user_id=uid))

# =========================================================
# CLEAN WAIT SIGNALS
# =========================================================

async def cleanwaits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    from database import get_db
    conn = get_db()
    cursor = conn.execute("DELETE FROM signals WHERE direction = 'WAIT'")
    conn.commit()
    count = cursor.rowcount
    await update.message.reply_text(f"{count} signaux WAIT supprimés")

# DB QUERY
# =========================================================

@check_limit
async def dbquery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /dbquery <SQL>")
        return
    sql = " ".join(context.args)
    try:
        from database import get_db
        conn = get_db()
        rows = conn.execute(sql).fetchall()
        if not rows:
            await update.message.reply_text("Requete OK, 0 resultats")
            return
        text = ""
        for r in rows[:20]:
            text += str(dict(r)) + "\n"
        if len(rows) > 20:
            text += f"\n... et {len(rows) - 20} de plus"
        await update.message.reply_text(text[:4000])
    except Exception as e:
        await update.message.reply_text(f"Erreur: {e}")

async def exportsignals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    signals = history_mgr.get_recent_signals(1000)
    if not signals:
        await update.message.reply_text("Aucun signal a exporter")
        return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Symbole", "Direction", "Entree", "SL", "TP", "Score",
        "Timeframe", "Validation", "Raison validation", "Statut", "Raison rejet",
        "Prix resultat", "PnL%", "PnL", "Capital avant", "Capital apres", "RR", "Classe actif", "Parametres",
        "Ouvert", "Ferme"
    ])
    for s in signals:
        from datetime import datetime
        created = datetime.utcfromtimestamp(s['created_at']).strftime('%Y-%m-%d %H:%M') if s.get('created_at') else ''
        closed = datetime.utcfromtimestamp(s['closed_at']).strftime('%Y-%m-%d %H:%M') if s.get('closed_at') else ''
        writer.writerow([
            s.get('id', ''),
            s.get('symbol', ''),
            s.get('direction', ''),
            s.get('entry_price', ''),
            s.get('sl', ''),
            s.get('tp', ''),
            s.get('score', ''),
            s.get('timeframe', ''),
            s.get('validation_status', ''),
            s.get('validation_reason', ''),
            s.get('status', ''),
            s.get('rejection_reason', ''),
            s.get('result_price', ''),
            s.get('result_pct', ''),
            s.get('pnl', ''),
            s.get('capital_before', ''),
            s.get('capital_after', ''),
            s.get('rr_ratio', ''),
            s.get('asset_class', ''),
            s.get('params_used', ''),
            created,
            closed
        ])
    output.seek(0)
    await update.message.reply_document(
        document=output.getvalue().encode('utf-8'),
        filename='signals_export.csv',
        caption=f'{len(signals)} signaux exportes'
    )

async def refreshhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    lang = user_mgr.get_setting(update.effective_user.id, "lang", "en")
    await update.message.reply_text(get_text(lang, "refreshhistory_start"))
    from bot_handlers import check_signal_outcomes
    await check_signal_outcomes(context.bot)
    await update.message.reply_text(get_text(lang, "refreshhistory_done"))

# =========================================================
# CLEAR HISTORY
# =========================================================

@check_limit
async def clearhistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    lang = user_mgr.get_setting(update.effective_user.id, "lang", "en")
    history_mgr.clear_all_signals()
    await update.message.reply_text(get_text(lang, "clearhistory_done"))

# =========================================================
# DELETE USER
# =========================================================

@check_limit
async def deleteuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /deleteuser <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID invalide")
        return
    if user_mgr.delete_user(uid):
        await update.message.reply_text(f"🗑️ Utilisateur {uid} supprimé avec toutes ses données")
    else:
        await update.message.reply_text(f"❌ Utilisateur {uid} introuvable")


# =========================================================
# AUTOTRADE ADMIN COMMANDS
# =========================================================

try:
    from trading_handlers import (
        admin_cmd_trading_stats as _base_trading_stats,
        admin_cmd_trades as _base_trades,
        admin_cmd_forceclose as _base_forceclose,
    )
except ImportError as _imp_err:
    logger.error("Failed to import admin trading commands from trading_handlers: %s", _imp_err)
    _base_trading_stats = None
    _base_trades = None
    _base_forceclose = None

async def admin_cmd_trading_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    if _base_trading_stats is None:
        await update.message.reply_text("⚠️ Commande /trading_stats indisponible.")
        return
    await _base_trading_stats(update, context)

async def admin_cmd_trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    if _base_trades is None:
        await update.message.reply_text("⚠️ Commande /trades indisponible.")
        return
    await _base_trades(update, context)

async def admin_cmd_forceclose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin_user(update):
        return
    if _base_forceclose is None:
        await update.message.reply_text("⚠️ Commande /forceclose indisponible.")
        return
    await _base_forceclose(update, context)
