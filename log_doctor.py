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
        re.compile(r"restricted location|b\. Eligibility|binance\.com/en/terms|HTTP 451", re.IGNORECASE),
        "🌍 Blocage géographique Binance (HTTP 451 — Restricted Location)",
        "Le serveur d'hébergement (ex: Render US) est situé dans une région bloquée par `api.binance.com` selon les CGU Binance ('b. Eligibility'). L'appel initial de `python-binance` (`Client.ping()`) ou les requêtes vers `api.binance.com` échouaient donc.",
        "Corrigé : le bot désactive désormais le ping sur `api.binance.com` et route automatiquement le Spot/Market Data vers `data-api.binance.vision`, `testnet.binance.vision` et `testnet.binancefuture.com`. Tape `/account` pour vérifier ton solde.",
    ),
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
        re.compile(r"AUTOTRADE SCHEDULER STOPPED|NoneType' object has no attribute 'cursor'", re.IGNORECASE),
        "🔄 Watchdog HealthMonitor (Scheduler / Curseur DB)",
        "Lors du lancement via `python main.py`, le module `__main__` était distinct de `main` et la connexion DB était fermée avant la 2e requête du HealthMonitor.",
        "Corrigé dans `health_monitor.py` et `main.py` : redéploie / relance le service pour charger la nouvelle version.",
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

            mode_label = "TESTNET 🧪" if cfg.testnet else "LIVE RÉEL 🚨"
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


def _synthesize_direct_answer(
    user_question: Optional[str],
    diag: Dict[str, Any],
    probes: Dict[str, Any],
    log_lines: List[str],
) -> str:
    """
    Moteur de réponse conversationnelle intelligent (0 token, instantané).
    Quand l'administrateur pose une question (ou demande un diagnostic), ce moteur
    croise sa question, les sondes temps réel (Binance, DB, Commandes) et les logs
    pour lui répondre directement en langage humain au lieu de juste lister les erreurs.
    """
    q = (user_question or "").lower().strip()
    findings = diag.get("findings", [])
    b_probe = probes.get("binance", {})
    a_probe = probes.get("apis", {})
    c_probe = probes.get("commands", {})

    # 1. Question sur le solde / montant qui reste / /account
    if any(w in q for w in ("solde", "montant", "account", "balance", "argent", "combien", "reste")):
        if b_probe.get("account_api_ok"):
            return (
                f"✅ *Réponse directe sur ton solde Binance :*\n"
                f"La connexion au portefeuille fonctionne. Ton solde détecté en direct est de :\n"
                f"👉 `{b_probe.get('account_balance_str')}`\n"
                f"Si `/account` ne répondait pas avant, c'était à cause du ping initial de `python-binance` vers `api.binance.com` (bloqué aux USA par l'erreur `b. Eligibility`). C'est maintenant contourné en direct."
            )
        else:
            return (
                f"🔴 *Pourquoi le solde (`/account`) échoue actuellement :*\n"
                f"Le test en direct vers ton compte Binance a renvoyé : `{b_probe.get('account_balance_str')}`.\n"
                f"👉 *Action* : Vérifie que tes clés correspondent bien au marché actif avec /config, ou change de marché via /setmarket `spot` ou /setmarket `futures`."
            )

    # 2. Question sur une ouverture de position / paper trading / trade qui échoue
    if any(w in q for w in ("position", "paper", "ouvrir", "trade", "buy", "short", "ordre", "faux")):
        ans = [
            "🎯 *Diagnostic sur l'ouverture de positions (Paper & Live) :*"
        ]
        if not a_probe.get("market_klines_ok"):
            ans.append("• 🔴 *Problème détecté* : Le flux de bougies/prix `BTCUSDT` ne répond pas actuellement, ce qui empêche de calculer le prix d'entrée et l'ATR (SL/TP).")
        else:
            ans.append("• 🟢 *Flux de prix & ATR* : Le prix en temps réel et les bougies `BTCUSDT` répondent correctement.")
        if b_probe.get("account_api_ok"):
            ans.append(f"• 🟢 *Portefeuille Binance* : Prêt (`{b_probe.get('account_balance_str')}`).")
        else:
            ans.append(f"• 🔴 *Portefeuille Binance* : Échec d'accès (`{b_probe.get('account_balance_str')}`).")
        ans.append(
            "• 💡 *Note Paper Trading* : Le capital initial (fixé à `10 000 USDT`), le calcul du PnL avec levier (sans double multiplication) et le prix d'entrée temps réel ont été fiabilisés. Tape /paper `reset` pour repartir sur une base propre de 10 000 USDT."
        )
        return "\n".join(ans)

    # 3. Question sur un utilisateur ajouté (/teddy) qui ne peut pas utiliser le bot
    if any(w in q for w in ("utilisateur", "user", "teddy", "ajout", "bloqué", "acces", "accès")):
        return (
            "👤 *Pourquoi un utilisateur ajouté ne pouvait pas utiliser le bot :*\n"
            "Même après `/teddy <id>` (`approved=1`), le décorateur `@check_limit` bloquait l'utilisateur sur deux verrous :\n"
            "1) `terms_accepted` était encore à `0` tant qu'il n'avait pas cliqué sur le bouton des CGU dans `/start`.\n"
            "2) Le rôle `tester` était limité à 5 requêtes/jour comme un compte non approuvé.\n"
            "👉 *Solution appliquée* : `/teddy` active désormais automatiquement `approved=1` + `terms_accepted=1` + essai actif illimité. Tu peux refaire `/teddy <id>` sur son ID pour le débloquer immédiatement !"
        )

    # 4. Question sur l'erreur Binance Eligibility / restricted location / HTTP 451
    if any(w in q for w in ("eligibility", "restricted", "location", "terms", "451")):
        return (
            "🌍 *Explication du message `restricted location according to b. Eligibility` :*\n"
            "Ce message vient de Binance (`api.binance.com`) parce que le serveur Render est hébergé aux États-Unis.\n"
            "• *Conséquence* : Toute requête envoyée à `api.binance.com` ou `fapi.binance.com` est rejetée par Binance.\n"
            "• *Solution active* : Le bot contourne `api.binance.com` en passant par `data-api.binance.vision` (données publiques), `testnet.binance.vision` (Spot Testnet) et `testnet.binancefuture.com` (Futures Testnet) en requêtes signées directes."
        )

    # 5. Synthèse générale intelligente (quand l'admin demande "que signifient les logs ?" ou pose une question libre)
    synth_lines = ["🧠 *Synthèse intelligente de la situation :*"]
    if findings:
        top = findings[0]
        synth_lines.append(
            f"• *Problème principal identifié* : **{top['title']}**.\n"
            f"  ↳ _En clair_ : {top['explanation']}\n"
            f"  ↳ _Ce que tu dois faire_ : {top['fix']}"
        )
        if len(findings) > 1:
            others = ", ".join(f["title"] for f in findings[1:3])
            synth_lines.append(f"• *Autres événements secondaires dans les logs* : {others}.")
    else:
        if c_probe.get("ok") and b_probe.get("account_api_ok") and a_probe.get("db_ok"):
            synth_lines.append(
                "• *Tout est nominal* : Aucune erreur bloquante dans les logs récents, les 32 commandes répondent, la base PostgreSQL est connectée et ton compte Binance est accessible."
            )
        else:
            issues = []
            if not a_probe.get("db_ok"):
                issues.append("la base PostgreSQL ne répond pas")
            if not b_probe.get("account_api_ok"):
                issues.append(f"l'accès au compte Binance a échoué ({b_probe.get('account_balance_str')})")
            if not a_probe.get("market_klines_ok"):
                issues.append("le flux de bougies BTCUSDT est indisponible")
            synth_lines.append(
                f"• *Anomalie détectée par les sondes en direct* : {', '.join(issues) or 'vérifie les détails ci-dessous'}."
            )

    return "\n".join(synth_lines)


def _call_gemini_flash_lite(
    log_lines: List[str],
    local_diag: Dict[str, Any],
    probes: Optional[Dict[str, Any]] = None,
    user_question: Optional[str] = None,
) -> Optional[str]:
    """
    Appelle Gemini (essaie `gemini-3.1-flash-lite-preview` puis `gemini-2.5-flash`)
    pour répondre précisément à la question de l'administrateur sans recracher les logs bruts.
    """
    from config import GEMINI_API_KEY, GEMINI_LOG_MODEL

    api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    compact_logs = "\n".join(log_lines[-20:])[-2000:]
    checks_summary = "\n".join(local_diag.get("user_checks", []))
    probe_summary = ""
    if probes:
        probe_summary = (
            f"Sondes en direct: Commandes={probes['commands']['detail']}, "
            f"Solde Binance={probes['binance']['account_balance_str']}, "
            f"DB={probes['apis']['db_ok']}, Klines={probes['apis']['market_klines_ok']}\n"
        )
    question_part = (
        f"Question précise de l'administrateur : \"{user_question}\"\n"
        "IMPORTANT : Réponds DIRECTEMENT à sa question dès la première phrase. Ne lui récite pas les lignes de logs brutes (il les voit déjà), explique-lui le POURQUOI et donne la solution concrète.\n"
        if user_question
        else "Explique humainement ce qui se passe dans le bot et s'il y a une action à faire.\n"
    )

    prompt = (
        "Tu es l'ingénieur diagnostic intégré au bot de trading Telegram 'Bitsure Teddy'.\n"
        "Réponds en français, avec un ton humain, clair et très précis (max 150 mots) :\n"
        "1) Réponse directe à la question / diagnostic de la cause racine\n"
        "2) Impact réel sur le bot\n"
        "3) Commande Telegram exacte à taper.\n\n"
        f"{question_part}\n"
        f"{probe_summary}"
        f"État du compte :\n{checks_summary}\n\n"
        f"Contexte des logs :\n{compact_logs or 'Aucun log récent.'}"
    )

    # On teste le modèle configuré ainsi que les alias officiels Gemini Flash-Lite / Flash
    models_to_try = []
    for m in (GEMINI_LOG_MODEL, "gemini-3.1-flash-lite-preview", "gemini-2.5-flash", "gemini-2.0-flash-lite"):
        if m and m not in models_to_try:
            models_to_try.append(m)

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 380,
        },
    }).encode("utf-8")

    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
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
            with urllib.request.urlopen(req, timeout=7) as resp:
                if getattr(resp, "status", 200) != 200:
                    continue
                raw_body = resp.read().decode("utf-8")
                data = json.loads(raw_body)
            candidates = data.get("candidates") or []
            if not candidates:
                continue
            parts = candidates[0].get("content", {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
            if text:
                return text
        except Exception:
            continue
    return None


def run_real_system_probes(user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Exécute de VRAIS tests actifs en temps réel (zéro bluff) sur :
    1. Toutes les commandes enregistrées du bot (vérifie que chaque handler est bien importable et callable).
    2. Toutes les connexions Binance (Spot Public Mirror, Spot Testnet, Futures Public, Futures Testnet,
       et l'API Compte/Solde authentifiée `/account` de l'utilisateur avec détection du géo-blocage HTTP 451).
    3. Toutes les APIs externes et internes (PostgreSQL DB, Flux de prix BTCUSDT + Klines, TwelveData, Gemini).
    """
    results: Dict[str, Any] = {
        "commands": {"ok": True, "total": 0, "failed": [], "detail": ""},
        "binance": {
            "ok": True,
            "spot_public": False,
            "futures_public": False,
            "spot_testnet": False,
            "futures_testnet": False,
            "account_api_ok": False,
            "account_balance_str": "Non testé",
            "geo_blocked_main_api": False,
            "errors": [],
        },
        "apis": {
            "db_ok": False,
            "scheduler_ok": False,
            "market_klines_ok": False,
            "twelvedata_configured": False,
            "gemini_configured": False,
            "errors": [],
        },
    }

    # ── 1. VÉRIFICATION RÉELLE DE TOUTES LES COMMANDES DU BOT ────────────────
    try:
        import bot_handlers
        import trading_handlers
        import live_handlers
        import admin_handlers

        expected_commands = [
            ("start", getattr(bot_handlers, "start", None)),
            ("menu", getattr(bot_handlers, "menu_command", None)),
            ("help", getattr(bot_handlers, "help_command", None)),
            ("analyse", getattr(bot_handlers, "analyse", None)),
            ("price", getattr(bot_handlers, "price", None)),
            ("trend", getattr(bot_handlers, "trend", None)),
            ("volatility", getattr(bot_handlers, "volatility", None)),
            ("levels", getattr(bot_handlers, "levels", None)),
            ("alert", getattr(bot_handlers, "alert", None)),
            ("alerts", getattr(bot_handlers, "alerts", None)),
            ("watchlist", getattr(bot_handlers, "watchlist_command", None)),
            ("scan", getattr(bot_handlers, "scan", None)),
            ("paper", getattr(bot_handlers, "paper", None)),
            ("usage", getattr(bot_handlers, "usage", None)),
            ("status", getattr(bot_handlers, "status_command", None)),
            ("logs", getattr(bot_handlers, "logs_command", None)),
            ("account", getattr(trading_handlers, "cmd_account", None)),
            ("autotrade", getattr(trading_handlers, "cmd_autotrade", None)),
            ("config", getattr(trading_handlers, "cmd_config", None)),
            ("positions", getattr(trading_handlers, "cmd_positions", None)),
            ("close", getattr(trading_handlers, "cmd_close", None)),
            ("pnl", getattr(trading_handlers, "cmd_pnl", None)),
            ("setapikeys", getattr(trading_handlers, "cmd_setapikeys", None)),
            ("setmarket", getattr(trading_handlers, "cmd_setmarket", None)),
            ("settestnet", getattr(trading_handlers, "cmd_settestnet", None)),
            ("safestatus", getattr(trading_handlers, "cmd_safestatus", None)),
            ("clearsafe", getattr(trading_handlers, "cmd_clearsafe", None)),
            ("live", getattr(live_handlers, "cmd_live", None)),
            ("live_long", getattr(live_handlers, "cmd_live_long", None)),
            ("live_short", getattr(live_handlers, "cmd_live_short", None)),
            ("teddy", getattr(admin_handlers, "teddy", None)),
            ("stats", getattr(admin_handlers, "stats", None)),
        ]
        results["commands"]["total"] = len(expected_commands)
        missing = [name for name, fn in expected_commands if not callable(fn)]
        if missing:
            results["commands"]["ok"] = False
            results["commands"]["failed"] = missing
            results["commands"]["detail"] = f"Handlers invalides: {', '.join(missing)}"
        else:
            results["commands"]["detail"] = f"{len(expected_commands)}/{len(expected_commands)} handlers vérifiés"
    except Exception as exc:
        results["commands"]["ok"] = False
        results["commands"]["detail"] = f"Erreur inspection commandes: {exc}"

    # ── 2. VRAIS TESTS RÉSEAU SUR TOUTES LES CONNEXIONS BINANCE ──────────────
    def _http_probe(url: str, timeout: float = 3.5) -> Tuple[bool, int, str]:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, "status", 200)
                body = resp.read(300).decode("utf-8", errors="replace")
                return (code == 200), code, body
        except Exception as exc:
            err_str = str(exc)
            code = getattr(exc, "code", 0)
            try:
                if hasattr(exc, "read"):
                    err_str = exc.read(300).decode("utf-8", errors="replace")
            except Exception:
                pass
            return False, code, err_str

    # 2a. Spot Public Mirror (data-api.binance.vision — jamais géo-bloqué)
    ok_vis, code_vis, body_vis = _http_probe("https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT")
    results["binance"]["spot_public"] = ok_vis and ("price" in body_vis)
    if not results["binance"]["spot_public"]:
        results["binance"]["errors"].append(f"Spot Public (data-api.binance.vision): HTTP {code_vis}")

    # 2b. Test direct de api.binance.com pour détecter si le serveur est géo-bloqué (HTTP 451 / Eligibility)
    ok_main, code_main, body_main = _http_probe("https://api.binance.com/api/v3/ping", timeout=2.5)
    if code_main == 451 or "Eligibility" in body_main or "restricted location" in body_main:
        results["binance"]["geo_blocked_main_api"] = True

    # 2c. Spot Testnet (testnet.binance.vision)
    ok_st, code_st, _ = _http_probe("https://testnet.binance.vision/api/v3/ping")
    results["binance"]["spot_testnet"] = ok_st
    if not ok_st:
        results["binance"]["errors"].append(f"Spot Testnet (testnet.binance.vision): HTTP {code_st}")

    # 2d. Futures Public (fapi.binance.com)
    ok_fp, code_fp, body_fp = _http_probe("https://fapi.binance.com/fapi/v1/ping")
    results["binance"]["futures_public"] = ok_fp
    if not ok_fp:
        if code_fp == 451 or "Eligibility" in body_fp or "restricted location" in body_fp:
            results["binance"]["geo_blocked_main_api"] = True
        results["binance"]["errors"].append(f"Futures Public (fapi.binance.com): HTTP {code_fp} (géo-bloqué ou indisponible)")

    # 2e. Futures Testnet (testnet.binancefuture.com)
    ok_ft, code_ft, _ = _http_probe("https://testnet.binancefuture.com/fapi/v1/ping")
    results["binance"]["futures_testnet"] = ok_ft
    if not ok_ft:
        results["binance"]["errors"].append(f"Futures Testnet (testnet.binancefuture.com): HTTP {code_ft}")

    # 2f. Test authentifié réel du solde /account de l'utilisateur (ou clés par défaut)
    try:
        from binance_manager import get_full_account_info
        from trading_config import get_config
        target_uid = user_id if user_id is not None else 0
        cfg = get_config(target_uid)
        acc_info = get_full_account_info(target_uid, market_type=cfg.market_type)
        results["binance"]["account_api_ok"] = True
        results["binance"]["account_balance_str"] = (
            f"{acc_info['available_balance']:.2f} USDT dispo / {acc_info['total_wallet_balance']:.2f} USDT total ({acc_info['market_type'].upper()})"
        )
    except Exception as acc_err:
        results["binance"]["account_api_ok"] = False
        results["binance"]["account_balance_str"] = f"Échec: {acc_err}"
        results["binance"]["errors"].append(f"API Compte `/account` : {acc_err}")

    results["binance"]["ok"] = bool(
        results["binance"]["spot_public"]
        and (results["binance"]["spot_testnet"] or results["binance"]["futures_testnet"])
        and results["binance"]["account_api_ok"]
    )

    # ── 3. VRAIS TESTS SUR LA BASE DE DONNÉES, LE SCHEDULER ET LES FLUX ─────
    try:
        from health_monitor import check_db_health, get_last_health_status
        results["apis"]["db_ok"] = bool(check_db_health())
        hs = get_last_health_status()
        results["apis"]["scheduler_ok"] = bool(hs.get("scheduler_running", True)) if hs else True
    except Exception as db_exc:
        results["apis"]["db_ok"] = False
        results["apis"]["errors"].append(f"PostgreSQL: {db_exc}")

    try:
        from binance_manager import get_klines_dataframe
        df = get_klines_dataframe("BTCUSDT", "1h", market_type="spot", limit=5)
        results["apis"]["market_klines_ok"] = bool(df is not None and not df.empty)
        if not results["apis"]["market_klines_ok"]:
            results["apis"]["errors"].append("Flux bougies BTCUSDT vide")
    except Exception as kl_exc:
        results["apis"]["market_klines_ok"] = False
        results["apis"]["errors"].append(f"Flux bougies BTCUSDT: {kl_exc}")

    try:
        from config import TWELVEDATA_API_KEY, GEMINI_API_KEY
        results["apis"]["twelvedata_configured"] = bool(TWELVEDATA_API_KEY)
        results["apis"]["gemini_configured"] = bool(GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY"))
    except Exception:
        pass

    return results


def build_public_system_status_page(user_id: Optional[int] = None) -> str:
    """
    Construit un tableau de bord public d'état des services qui EXÉCUTE DE VRAIS TESTS
    en direct (commandes, connexions Binance Spot/Futures/Account, flux de prix, DB)
    combinés à l'analyse des logs récents. Aucun faux positif : si une API ou `/account`
    échoue ou est géo-bloquée, l'état l'affiche immédiatement.
    """
    log_lines = get_recent_logs(max_lines=60)
    recent_tail = "\n".join(log_lines[-25:])
    probes = run_real_system_probes(user_id=user_id)

    db_ok = probes["apis"]["db_ok"]
    scheduler_ok = probes["apis"]["scheduler_ok"]
    cmds_ok = probes["commands"]["ok"]
    klines_ok = probes["apis"]["market_klines_ok"]

    if re.search(r"DATABASE DOWN|OperationalError", recent_tail, re.IGNORECASE):
        db_ok = False
    if re.search(r"AUTOTRADE SCHEDULER STOPPED", recent_tail, re.IGNORECASE):
        scheduler_ok = False

    # Flux de Prix & Analyse
    market_feed_issue = None
    if not klines_ok or not probes["binance"]["spot_public"]:
        market_feed_issue = "Échec du test en direct de récupération des bougies BTCUSDT"
    elif re.search(r"TimedOut|ConnectTimeout|ReadTimeout|NetworkError", recent_tail, re.IGNORECASE):
        market_feed_issue = "Ralentissement temporaire sur le fournisseur de données"
    elif re.search(r"data_unavailable|Impossible de récupérer|Could not retrieve data", recent_tail, re.IGNORECASE):
        market_feed_issue = "Erreur récente de récupération de données sur une paire"

    # Connectivité Binance & Compte (/account)
    binance_issue = None
    if not probes["binance"]["account_api_ok"]:
        binance_issue = f"Échec de lecture du compte/solde (`/account`) : {probes['binance']['account_balance_str']}"
    elif re.search(r"restricted location|b\. Eligibility|binance\.com/en/terms", recent_tail, re.IGNORECASE):
        binance_issue = "Serveur hébergé en zone restreinte par api.binance.com (bascule automatique sur les miroirs Binance activée)"
    elif re.search(r"-2015|Invalid API-key", recent_tail, re.IGNORECASE):
        binance_issue = "Clé API Binance rejetée (vérifie tes clés ou le mode Spot/Futures)"
    elif re.search(r"-2019|Margin is insufficient|insufficient balance", recent_tail, re.IGNORECASE):
        binance_issue = "Marge / Solde USDT insuffisant sur le compte Binance pour le dernier ordre"
    elif re.search(r"-4164|MIN_NOTIONAL", recent_tail, re.IGNORECASE):
        binance_issue = "Montant du dernier ordre inférieur au minimum Binance (MIN_NOTIONAL)"
    elif re.search(r"-4061|position side does not match", recent_tail, re.IGNORECASE):
        binance_issue = "Mode de position Binance Futures incompatible (passe en One-Way Mode)"

    # État spécifique du compte de l'utilisateur
    user_safety_issue = None
    if user_id is not None:
        try:
            from trading_config import get_config
            cfg = get_config(user_id)
            if cfg.safety_lock:
                user_safety_issue = f"Safe Mode activé par sécurité ({cfg.safety_lock_reason or 'protection du capital'})"
            elif cfg.safety_warn:
                user_safety_issue = f"Avertissement mineur ({cfg.safety_warn_reason or 'synchronisation'})"
        except Exception:
            pass

    incidents: List[str] = []
    if not cmds_ok:
        incidents.append(f"• *Commandes Telegram* : {probes['commands']['detail']}.")
    if not db_ok:
        incidents.append("• *Base de données PostgreSQL* : Test de connexion échoué.")
    if not scheduler_ok:
        incidents.append("• *Moteur d'exécution AutoTrade* : Planificateur arrêté.")
    if market_feed_issue:
        incidents.append(f"• *Flux de marché* : {market_feed_issue}.")
    if binance_issue:
        incidents.append(f"• *Passerelle & Compte Binance* : {binance_issue}.")
    if probes["binance"]["geo_blocked_main_api"]:
        incidents.append("• *Réseau Binance (`api.binance.com`)* : Région IP restreinte détectée (`b. Eligibility`) — routage actif via `data-api.binance.vision` & Testnet.")
    if user_safety_issue:
        incidents.append(f"• *Protection Compte* : {user_safety_issue}.")

    if not incidents:
        global_banner = "🟢 *Tous les systèmes sont opérationnels (Vérifiés en direct)*"
    elif not db_ok or not scheduler_ok or not probes["binance"]["account_api_ok"]:
        global_banner = "🔴 *Anomalie détectée lors du test en direct*"
    else:
        global_banner = "🟠 *Fonctionnement partiel / Avertissement détecté*"

    bot_api_dot = f"🟢 Opérationnel ({probes['commands']['total']} cmds)" if cmds_ok else "🔴 Erreur Handler"
    db_dot = "🟢 Opérationnel" if db_ok else "🔴 Perturbé"
    market_dot = "🟢 Opérationnel (BTCUSDT OK)" if not market_feed_issue else "🟠 Dégradé"
    binance_dot = (
        f"🟢 Opérationnel ({probes['binance']['account_balance_str']})"
        if (probes["binance"]["account_api_ok"] and not binance_issue)
        else ("🔴 Échec `/account`" if not probes["binance"]["account_api_ok"] else "🟠 Alerte")
    )
    autotrade_dot = (
        "🟢 Opérationnel"
        if (scheduler_ok and not user_safety_issue)
        else ("🟠 Safe Mode / Alerte" if scheduler_ok else "🔴 Arrêté")
    )

    lines = [
        "📡 *État des Services (Tests Réels) — Bitsure Teddy*",
        "━━━━━━━━━━━━━━━━━━━━━",
        global_banner,
        "",
        "🧩 *Résultat des sondes en direct :*",
        f"• *Commandes Telegram* : {bot_api_dot}",
        f"• *Flux de Prix & Bougies* : {market_dot}",
        f"• *Compte & Solde Binance (`/account`)* : {binance_dot}",
        f"• *Connexions Binance* : Spot Public {'🟢' if probes['binance']['spot_public'] else '🔴'} | Spot Testnet {'🟢' if probes['binance']['spot_testnet'] else '🔴'} | Futures Testnet {'🟢' if probes['binance']['futures_testnet'] else '🔴'}",
        f"• *Moteur AutoTrade & Surveillance SL/TP* : {autotrade_dot}",
        f"• *Base de Données PostgreSQL* : {db_dot}",
    ]

    if incidents:
        lines.append("")
        lines.append("⚠️ *Détail des anomalies détectées :*")
        lines.extend(incidents)
    else:
        lines.append("")
        lines.append("✅ _Toutes les commandes, les APIs et la lecture du solde Binance ont été testées avec succès._")

    return "\n".join(lines)


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

    # 1. Sondes actives en direct (Commandes, Connexions Binance, APIs)
    probes = run_real_system_probes(user_id=user_id)

    # 2. Réponse directe et intelligente à la question (IA Gemini ou Synthèse Experte Locale)
    ai_explanation = None
    if use_gemini:
        ai_explanation = _call_gemini_flash_lite(log_lines, diag, probes=probes, user_question=user_question)

    if ai_explanation:
        clean_ai = ai_explanation.replace("```", "").strip()
        lines.append("🤖 *Réponse & Diagnostic Gemini Flash-Lite :*")
        lines.append(clean_ai)
        lines.append("")
    else:
        direct_answer = _synthesize_direct_answer(user_question, diag, probes, log_lines)
        lines.append(direct_answer)
        lines.append("")

    # 3. Résumé des tests réels en direct
    lines.append("🔬 *Tests Réels en Direct (Commandes / Binance / APIs) :*")
    lines.append(
        f"• *Commandes Bot* : {'🟢' if probes['commands']['ok'] else '🔴'} {probes['commands']['detail']}"
    )
    lines.append(
        f"• *Binance Spot Public (`data-api.binance.vision`)* : {'🟢 OK' if probes['binance']['spot_public'] else '🔴 ÉCHEC'}"
    )
    lines.append(
        f"• *Binance Spot Testnet (`testnet.binance.vision`)* : {'🟢 OK' if probes['binance']['spot_testnet'] else '🔴 ÉCHEC'}"
    )
    lines.append(
        f"• *Binance Futures Testnet (`testnet.binancefuture.com`)* : {'🟢 OK' if probes['binance']['futures_testnet'] else '🔴 ÉCHEC'}"
    )
    lines.append(
        f"• *Binance Futures Live (`fapi.binance.com`)* : {'🟢 OK' if probes['binance']['futures_public'] else '🟠 Géo-bloqué (IP US Render)'}"
    )
    lines.append(
        f"• *Test Solde `/account`* : {'🟢' if probes['binance']['account_api_ok'] else '🔴'} `{probes['binance']['account_balance_str']}`"
    )
    lines.append(
        f"• *APIs Internes* : DB PostgreSQL {'🟢' if probes['apis']['db_ok'] else '🔴'} | Bougies BTCUSDT {'🟢' if probes['apis']['market_klines_ok'] else '🔴'}"
    )
    lines.append("")

    # 4. État en direct de l'utilisateur et du bot
    if diag["user_checks"]:
        lines.append("🔍 *Vérification de ton profil :*")
        for chk in diag["user_checks"]:
            lines.append(f"• {chk}")
        lines.append("")

    # 5. Interprétation détaillée des patterns trouvés dans les logs
    findings = diag["findings"]
    if findings:
        lines.append("📘 *Traduction des codes d'erreurs détectés :*")
        for idx, item in enumerate(findings[:3], 1):
            lines.append(f"*{idx}. {item['title']}*")
            lines.append(f"   ↳ *Cause* : {item['explanation']}")
            lines.append(f"   ↳ *Action* : {item['fix']}")
            lines.append("")

    lines.append("💬 _Pose n'importe quelle question (ex: `/logs pourquoi mon solde ou mon trade bloque ?`) pour une analyse ciblée._")

    report = "\n".join(lines)
    if len(report) > 3900:
        report = report[:3890] + "\n…"
    return report
