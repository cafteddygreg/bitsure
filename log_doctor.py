"""
log_doctor.py
-------------
Interpréteur intelligent de logs et diagnostic temps réel pour Bitsure Teddy.

Fonctionnalités :
1. Capture en mémoire (Ring Buffer) de tous les logs Python (`root` + `trading.log`)
   sans ralentir le bot et avec masquage automatique des clés API.
2. Moteur d'interprétation déterministe (0 token, instantané, 100% hors-ligne) qui
   traduit les erreurs techniques (Binance, PostgreSQL, Safe Mode, Telegram, Réseau,
   Commandes muettes) en explications claires en français avec la solution exacte.
3. Intégration optionnelle de Gemini (`gemini-3.1-flash-lite`, modèle ultra-léger et
   très peu coûteux en tokens) lorsque l'utilisateur pose une question libre ou
   souhaite une analyse approfondie, avec repli automatique sur le moteur local si
   aucune clé Gemini n'est configurée.
"""

import collections
import json
import logging
import os
import re
import time
import urllib.request
from typing import Deque, Dict, List, Optional, Tuple, Any

from trading_logger import LOG_PATH, RedactSensitiveFilter

_MAX_MEMORY_LOGS = 250
_MEMORY_LOG_BUFFER: Deque[str] = collections.deque(maxlen=_MAX_MEMORY_LOGS)
_BUFFER_ATTACHED = False

_API_KEY_RE = re.compile(r"[A-Za-z0-9]{40,}")


def _redact(text: str) -> str:
    if not text:
        return ""
    return _API_KEY_RE.sub("[REDACTED]", text)


class MemoryRingLogHandler(logging.Handler):
    """Capture les derniers logs en RAM pour diagnostic instantané sur Render."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _MEMORY_LOG_BUFFER.append(_redact(msg))
        except Exception:
            pass


def install_log_buffer() -> None:
    """Branche le ring-buffer sur le root logger et le logger trading."""
    global _BUFFER_ATTACHED
    if _BUFFER_ATTACHED:
        return
    handler = MemoryRingLogHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    handler.addFilter(RedactSensitiveFilter())

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    trading_logger = logging.getLogger("trading")
    trading_logger.addHandler(handler)

    _BUFFER_ATTACHED = True


# =========================================================
# BASE DE CONNAISSANCES DES ERREURS & SYMPTÔMES (0 TOKEN)
# =========================================================

_KNOWN_PATTERNS: List[Tuple[re.Pattern, str, str, str]] = [
    (
        re.compile(r"-2015|Invalid API-key, IP, or permissions", re.IGNORECASE),
        "🔑 Clé API Binance refusée (Code -2015)",
        "Binance rejette la clé API actuelle : soit la clé correspond au mauvais environnement (ex: clé Spot utilisée sur Futures ou clé Réelle utilisée en mode Testnet), soit les permissions Spot/Futures ne sont pas activées.",
        "Vérifie ton mode avec `/config` (`/settestnet on` ou `off` et `/setmarket spot` ou `futures`), ou enregistre tes clés avec `/setapikeys <key> <secret>`.",
    ),
    (
        re.compile(r"-2014|API-key format invalid", re.IGNORECASE),
        "🔑 Format de clé API Binance invalide (Code -2014)",
        "La clé API enregistrée contient des espaces, est tronquée ou n'est pas une clé HMAC valide.",
        "Réenregistre proprement tes clés via `/setapikeys <api_key> <api_secret>` en message privé.",
    ),
    (
        re.compile(r"-1021|Timestamp for this request", re.IGNORECASE),
        "⏱️ Décalage d'horloge serveur avec Binance (Code -1021)",
        "L'heure du serveur a dérivé de plus de quelques secondes par rapport aux serveurs Binance.",
        "Le bot resynchronise automatiquement ses requêtes au prochain appel. Si cela persiste, relance la commande dans 5 secondes.",
    ),
    (
        re.compile(r"-2019|Margin is insufficient|insufficient balance|Account has insufficient balance", re.IGNORECASE),
        "💰 Solde / Marge insuffisant(e) sur Binance (Code -2019)",
        "Le portefeuille Binance (Spot ou Futures Testnet/Live) n'a pas assez d'USDT disponibles pour couvrir la taille de la position et la marge requise.",
        "Vérifie ton solde via `/account` ou réduis le risque par trade avec `/setrisk 1` et le levier avec `/setleverage 1`.",
    ),
    (
        re.compile(r"-4164|notional must be no smaller than|MIN_NOTIONAL", re.IGNORECASE),
        "📏 Taille d'ordre inférieure au minimum Binance (MIN_NOTIONAL)",
        "La valeur totale de l'ordre (quantité × prix) est sous le minimum imposé par Binance (souvent 5 USDT en Spot ou 100 USDT sur BTCUSDT Futures).",
        "Augmente légèrement `/setrisk` ou `/setleverage`, ou vérifie le capital disponible avec `/account`.",
    ),
    (
        re.compile(r"-1111|Precision is over the maximum defined", re.IGNORECASE),
        "🔢 Précision décimale refusée par Binance (Code -1111)",
        "Le nombre de décimales sur la quantité ou le prix dépasse ce qu'autorise Binance pour ce symbole.",
        "Le bot arrondit via les filtres LOT_SIZE / PRICE_FILTER. Réessaie sur une paire majeure (`BTCUSDT`, `ETHUSDT`).",
    ),
    (
        re.compile(r"-4061|Order's position side does not match user's setting", re.IGNORECASE),
        "⚙️ Mode Hedge / One-Way incompatible sur Binance Futures (Code -4061)",
        "Ton compte Binance Futures est configuré en mode Hedge (Dual-Side) alors que le bot envoie des ordres en mode One-Way.",
        "Sur l'interface Binance Futures → Préférences → Mode de Position, sélectionne **One-Way Mode (Mode Unidirectionnel)**.",
    ),
    (
        re.compile(r"SAFE_MODE_ENGAGED|safety_lock|Safe mode critique", re.IGNORECASE),
        "🛡️ Safe Mode critique activé (`safety_lock`)",
        "Une erreur critique de protection (échec de pose de Stop-Loss sur Binance ou désynchronisation de position) a verrouillé l'ouverture de nouveaux trades pour protéger ton capital.",
        "Tape `/safestatus` pour voir la raison exacte, vérifie tes positions sur Binance, puis débloque avec `/clearsafe <ton_code_PIN>` (ou attends l'expiration automatique TTL d'1h).",
    ),
    (
        re.compile(r"SAFETY_WARN_ENGAGED|safety_warn|désynchronisation mineure", re.IGNORECASE),
        "⚠️ Avertissement de sécurité actif (`safety_warn`)",
        "Une anomalie temporaire a été détectée (ex: position fermée manuellement sur Binance ou délai réseau), mais le bot n'est PAS bloqué.",
        "Aucune action obligatoire : le bot continue de fonctionner et l'alerte s'efface au prochain cycle propre ou via `/clearsafe`.",
    ),
    (
        re.compile(r"SL_MISSING_CLOSE_FAILED|Échec pose SL", re.IGNORECASE),
        "🚨 Échec de pose du Stop-Loss sur Binance",
        "Le bot a ouvert une position mais Binance a refusé l'ordre Stop-Loss associé ; la fermeture d'urgence a donc été déclenchée.",
        "Vérifie immédiatement `/positions` et ton interface Binance, puis consulte `/safestatus`.",
    ),
    (
        re.compile(r"DATABASE DOWN|OperationalError|psycopg2|connection to server|pool", re.IGNORECASE),
        "🗄️ Erreur de connexion Base de Données PostgreSQL",
        "La base PostgreSQL a mis trop de temps à répondre ou la connexion a été coupée brièvement.",
        "Vérifie que `DATABASE_URL` est bien active sur Render. Le pool de connexions se reconnecte automatiquement au cycle suivant.",
    ),
    (
        re.compile(r"Can't parse entities|BadRequest: Message is not modified|BadRequest", re.IGNORECASE),
        "💬 Erreur de formatage Telegram (BadRequest)",
        "Telegram a refusé un message à cause d'un caractère spécial Markdown (`_`, `*`) ou parce que tu as cliqué deux fois sur un bouton qui affichait déjà le même texte.",
        "Sans gravité : le bot utilise désormais un repli automatique en texte brut pour garantir l'envoi de la réponse.",
    ),
    (
        re.compile(r"Conflict: terminated by other getUpdates request", re.IGNORECASE),
        "🔄 Conflit Telegram : deux instances du bot tournent en même temps",
        "Deux serveurs ou terminaux différents utilisent le même `TELEGRAM_TOKEN` en mode polling simultanément, ce qui fait qu'une commande sur deux ne répond pas !",
        "Arrête toute autre instance locale ou ancien déploiement Render pour qu'un seul processus utilise ce `TELEGRAM_TOKEN`.",
    ),
    (
        re.compile(r"TimedOut|ConnectTimeout|ReadTimeout|NetworkError|RetryError", re.IGNORECASE),
        "🌐 Délai réseau dépassé (Timeout API / Telegram)",
        "La requête vers Binance, Yahoo Finance ou Telegram a mis trop de temps à répondre.",
        "Problème réseau temporaire. Réessaie la commande dans quelques secondes.",
    ),
    (
        re.compile(r"data_unavailable|Impossible de récupérer|empty|No data", re.IGNORECASE),
        "📉 Données de marché indisponibles pour ce symbole",
        "Le fournisseur de prix n'a pas renvoyé de bougies historiques pour cette paire ou ce timeframe.",
        "Utilise un symbole standardisé comme `BTCUSDT`, `ETHUSDT` ou `XAUUSD` et vérifie la source avec `/switchapi` (admin).",
    ),
]


def get_recent_logs(max_lines: int = 80) -> List[str]:
    """Récupère les dernières lignes de logs (depuis la RAM + fichier trading.log)."""
    lines: List[str] = []

    if os.path.exists(LOG_PATH):
        try:
            with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                file_lines = [line.strip() for line in f.readlines() if line.strip()]
                lines.extend(file_lines[-max_lines:])
        except Exception:
            pass

    for mem_line in list(_MEMORY_LOG_BUFFER):
        if mem_line not in lines:
            lines.append(mem_line)

    return [_redact(line) for line in lines[-max_lines:]]


def analyze_logs_locally(
    log_lines: List[str],
    user_id: Optional[int] = None,
    user_question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyse déterministe et ultra-robuste des logs + de l'état utilisateur.
    Ne consomme aucun token et détecte pourquoi une commande ou un trade a échoué.
    """
    error_lines = [
        line for line in log_lines
        if any(lvl in line.upper() for lvl in ("ERROR", "CRITICAL", "WARNING", "EXCEPTION", "TRACEBACK", "SAFE_MODE"))
    ]

    matched_findings: List[Dict[str, str]] = []
    seen_titles = set()

    search_corpus = "\n".join(error_lines[-40:] if error_lines else log_lines[-40:])
    if user_question:
        search_corpus = f"{user_question}\n{search_corpus}"

    for pattern, title, explanation, fix in _KNOWN_PATTERNS:
        if pattern.search(search_corpus) and title not in seen_titles:
            seen_titles.add(title)
            matched_findings.append({
                "title": title,
                "explanation": explanation,
                "fix": fix,
            })

    # Diagnostic de l'état du compte / pourquoi une commande ne répond pas
    user_checks: List[str] = []
    if user_id is not None:
        try:
            from user_manager import UserManager
            um = UserManager.get_instance()
            if not um.can_access_bot(user_id):
                user_checks.append(
                    "🚫 *Accès non approuvé* : Ton compte n'est pas encore validé dans `users` (le bot bloque les commandes tant que `/teddy <ton_id>` n'est pas fait)."
                )
            elif not um.has_accepted_terms(user_id) and not um.is_admin(user_id):
                user_checks.append(
                    "📜 *CGU non acceptées* : Tu n'as pas encore cliqué sur « Accepter les conditions » via `/start`, ce qui bloque toutes les autres commandes."
                )
            elif not um.check_limit(user_id):
                user_checks.append(
                    "⏳ *Quota journalier atteint* : Tu as utilisé toutes tes requêtes gratuites du jour (`/usage`)."
                )
            else:
                user_checks.append("✅ *Autorisation & Quota Telegram* : Compte actif et autorisé à exécuter des commandes.")
        except Exception as e:
            user_checks.append(f"⚠️ Impossible de vérifier le profil utilisateur : `{e}`")

        try:
            from trading_config import get_config
            cfg = get_config(user_id)
            if cfg.safety_lock:
                user_checks.append(
                    f"🛑 *Safe Mode Critique ACTIF* : Raison = `{cfg.safety_lock_reason or 'Inconnue'}`. "
                    "Les ouvertures de trades sont bloquées jusqu'à `/clearsafe` ou expiration du TTL."
                )
            elif cfg.safety_warn:
                user_checks.append(
                    f"⚠️ *Avertissement Sécurité (`safety_warn`)* : `{cfg.safety_warn_reason or 'Anomalie mineure'}` (trading non bloqué)."
                )
            else:
                user_checks.append("🟢 *Safe Mode* : Aucun verrouillage actif (`safety_lock=False`).")

            mode_label = "TESTNET 🧪" if cfg.is_testnet else "LIVE RÉEL 🚨"
            user_checks.append(
                f"⚙️ *Profil AutoTrade* : Marché `{cfg.market_type.upper()}` | Mode `{mode_label}` | AutoTrade `{'ON' if cfg.auto_trade else 'OFF'}`"
            )
        except Exception as e:
            user_checks.append(f"⚠️ Lecture config trading : `{e}`")

    return {
        "total_lines_scanned": len(log_lines),
        "error_lines_count": len(error_lines),
        "recent_errors": error_lines[-8:],
        "findings": matched_findings,
        "user_checks": user_checks,
    }


def _call_gemini_flash_lite(
    log_lines: List[str],
    local_diag: Dict[str, Any],
    user_question: Optional[str] = None,
) -> Optional[str]:
    """
    Appelle le modèle économique Gemini (`gemini-3.1-flash-lite`) pour expliquer
    les logs ou répondre à une question précise de l'utilisateur.
    Utilise un prompt compact pour minimiser les tokens (< 600 tokens d'entrée).
    """
    from config import GEMINI_API_KEY, GEMINI_LOG_MODEL

    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    compact_logs = "\n".join(log_lines[-25:])[-2500:]
    checks_summary = "\n".join(local_diag.get("user_checks", []))
    question_part = (
        f"Question de l'utilisateur : {user_question}\n"
        if user_question
        else "Explique simplement ce que disent ces logs et s'il y a un problème à corriger.\n"
    )

    prompt = (
        "Tu es l'assistant de diagnostic technique intégré au bot de trading Telegram 'Bitsure Teddy'.\n"
        "Réponds en français, de manière directe, concise (max 140 mots) et structurée :\n"
        "1) Ce qui se passe exactement\n"
        "2) La cause précise\n"
        "3) La commande Telegram exacte à taper pour résoudre.\n"
        "N'utilise pas de blocs de code imbriqués complexes.\n\n"
        f"{question_part}\n"
        f"État du compte :\n{checks_summary}\n\n"
        f"Derniers logs (masqués) :\n{compact_logs or 'Aucun log récent.'}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_LOG_MODEL}:generateContent?key={api_key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 350,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "aistudio-build",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            raw_body = resp.read().decode("utf-8")
            data = json.loads(raw_body)
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None
    except Exception:
        return None


def build_log_diagnostic_report(
    user_id: Optional[int] = None,
    user_question: Optional[str] = None,
    use_gemini: bool = True,
) -> str:
    """
    Construit le rapport complet d'interprétation des logs (Local + Gemini Flash-Lite si disponible).
    """
    log_lines = get_recent_logs(max_lines=80)
    diag = analyze_logs_locally(log_lines, user_id=user_id, user_question=user_question)

    lines: List[str] = [
        "🩺 *Interpréteur de Logs & Diagnostic — Bitsure Teddy*",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]

    if user_question:
        lines.append(f"❓ *Ta question* : _{user_question}_")
        lines.append("")

    # 1. État en direct de l'utilisateur et du bot
    if diag["user_checks"]:
        lines.append("🔍 *Vérification rapide de ton profil & du bot :*")
        for chk in diag["user_checks"]:
            lines.append(f"• {chk}")
        lines.append("")

    # 2. Interprétation locale instantanée (0 token)
    findings = diag["findings"]
    if findings:
        lines.append("🧠 *Explication des erreurs détectées dans les logs :*")
        for idx, item in enumerate(findings[:4], 1):
            lines.append(f"*{idx}. {item['title']}*")
            lines.append(f"   ↳ *Signification* : {item['explanation']}")
            lines.append(f"   ↳ *Solution* : {item['fix']}")
            lines.append("")
    else:
        if diag["error_lines_count"] == 0:
            lines.append("✅ *Aucune erreur récente détectée dans les logs.*")
            lines.append(
                "💡 _Si une commande ne répond pas : vérifie que tu as bien accepté les conditions avec `/start`, "
                "ou qu'une deuxième copie du bot ne tourne pas en même temps._"
            )
            lines.append("")
        else:
            lines.append(
                f"ℹ️ *{diag['error_lines_count']} avertissement(s)/erreur(s) brut(s) trouvé(s)* (voir extrait ci-dessous)."
            )
            lines.append("")

    # 3. Interprétation IA économique (Gemini Flash-Lite) si activée ou si question posée
    if use_gemini:
        ai_explanation = _call_gemini_flash_lite(log_lines, diag, user_question=user_question)
        if ai_explanation:
            clean_ai = ai_explanation.replace("```", "").strip()
            lines.append("🤖 *Analyse Gemini Flash-Lite (éco-tokens) :*")
            lines.append(clean_ai)
            lines.append("")

    # 4. Extrait des dernières alertes/erreurs brutes
    recent_errs = diag["recent_errors"]
    if recent_errs:
        lines.append("📜 *Dernières lignes d'alerte/erreur (masquées) :*")
        for err_line in recent_errs[-4:]:
            short_line = err_line[-160:] if len(err_line) > 160 else err_line
            short_line = short_line.replace("`", "'").replace("*", "").replace("_", " ")
            lines.append(f"`{short_line}`")
    elif log_lines:
        lines.append("📜 *Dernière activité enregistrée :*")
        for info_line in log_lines[-3:]:
            short_line = info_line[-160:] if len(info_line) > 160 else info_line
            short_line = short_line.replace("`", "'").replace("*", "").replace("_", " ")
            lines.append(f"`{short_line}`")

    lines.append("")
    lines.append("💬 _Astuce : Tu peux écrire `/logs pourquoi ma commande ne répond pas ?` ou coller une erreur après `/logs` pour qu'il te l'explique._")

    report = "\n".join(lines)
    if len(report) > 3900:
        report = report[:3890] + "\n…"
    return report
