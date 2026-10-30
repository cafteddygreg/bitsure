"""
Audit de santé et de sécurité de Bitsure (rapport détaillé réservé à l'administrateur).

Ce que l'audit fait :
  - services : base de données, accès Binance, synchronisation de l'horloge, workers d'optimisation ;
  - configuration : secrets, mot de passe admin, origines CORS, HTTPS, mode debug ;
  - en-têtes HTTP de sécurité et comportement CORS (sonde réelle sur le serveur local) ;
  - routes : chaque route protégée est appelée SANS connexion et doit répondre 401/403 ; toute route publique
    qui n'est pas dans la liste attendue est signalée ;
  - clés Binance des utilisateurs : déchiffrables, sans droit de retrait ;
  - code : secrets oubliés, dépendances non figées, vulnérabilités connues (si pip-audit est installé).

Ce que l'audit NE fait PAS : il ne remplace pas un audit de code ni un test d'intrusion externe, et ne cherche pas
de failles de logique métier. Un rapport vert signifie « contrôles de configuration réussis », pas « site sécurisé ».
Aucune attaque n'est simulée : les sondes de routes sont des requêtes anonymes vides.

Les utilisateurs ne voient que `public_status()` (operational / degraded / checking) : aucun détail technique.
"""
from __future__ import annotations

import ast
import http.client
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
SEVERITIES = ("critical", "high", "medium", "low", "info")
INTERVAL_HOURS = float(os.getenv("SECURITY_AUDIT_INTERVAL_HOURS", "6") or 6)
ENABLED = os.getenv("SECURITY_AUDIT_ENABLED", "1") != "0"
AUTO_LOCK = os.getenv("SECURITY_AUDIT_AUTO_LOCK", "1") != "0"

# Routes publiques attendues (avant la « porte » d'authentification de web_api_server). Toute nouvelle route
# publique doit être ajoutée ici consciemment : sinon l'audit la signale.
EXPECTED_PUBLIC = {
    "GET": {
        "/api/auth/google/callback", "/api/auth/google/callback/", "/api/auth/google/url", "/api/auth/me",
        "/api/auth/sessions", "/api/demo/analyze", "/api/health", "/auth/callback", "/auth/callback/",
    },
    "POST": {
        "/api/auth/login", "/api/auth/logout", "/api/auth/register", "/api/user/accept-terms",
        "/api/user/telemetry",
        # Récupération de compte : publique par conception (l'utilisateur est déconnecté), limitée en débit.
        "/api/auth/recovery/request", "/api/auth/recovery/status", "/api/auth/recovery/message",
    },
}
# Routes « publiques » qui font leur propre authentification : on vérifie qu'elles refusent un appel anonyme.
SELF_AUTH_PUBLIC = {
    ("GET", "/api/auth/sessions"), ("POST", "/api/user/accept-terms"), ("POST", "/api/user/telemetry"),
}

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "running": False, "progress": None, "last": None, "history": deque(maxlen=20),
    "port": None, "last_lock_signature": None, "started": False,
}


# ---------------------------------------------------------------------------
# Structure d'un contrôle
# ---------------------------------------------------------------------------
def _chk(cid: str, category: str, status: str, severity: str, fr: str, en: str, detail_fr: str = "",
         detail_en: str = "", fix_fr: str = "", fix_en: str = "", auto_lock: bool = False) -> dict:
    """status : pass | fail | warn | info | skip. `severity` ne compte que si status != pass."""
    return {
        "id": cid, "category": category, "status": status, "severity": severity,
        "title_fr": fr, "title_en": en, "detail_fr": detail_fr, "detail_en": detail_en,
        "fix_fr": fix_fr, "fix_en": fix_en, "auto_lock": bool(auto_lock and status == "fail"),
    }


def configure(port: Optional[int] = None) -> None:
    if port:
        _state["port"] = int(port)


def _port() -> int:
    return int(_state.get("port") or os.environ.get("PORT") or os.environ.get("PYTHON_API_PORT") or 3000)


def _set_progress(step: int, total: int, fr: str, en: str) -> None:
    _state["progress"] = {"step": step, "total": total, "label_fr": fr, "label_en": en}


# ---------------------------------------------------------------------------
# Sondes HTTP locales
# ---------------------------------------------------------------------------
def _probe(method: str, path: str, headers: Optional[dict] = None, body: Optional[bytes] = None) -> tuple[int, dict]:
    conn = http.client.HTTPConnection("127.0.0.1", _port(), timeout=8)
    try:
        h = {"Host": "localhost", "User-Agent": "bitsure-security-audit", "Accept": "application/json"}
        h.update(headers or {})
        if body is not None:
            h["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=h)
        resp = conn.getresponse()
        resp.read()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Services
# ---------------------------------------------------------------------------
def check_services() -> List[dict]:
    out: List[dict] = []
    try:
        from health_monitor import check_db_health
        ok = bool(check_db_health())
    except Exception as exc:  # noqa: BLE001
        ok = False
        logger.warning("audit: base de données illisible: %s", exc)
    out.append(_chk("svc.database", "services", "pass" if ok else "fail", "critical",
                    "Base de données joignable", "Database reachable",
                    fix_fr="Vérifier DATABASE_URL, le serveur PostgreSQL et le pool de connexions.",
                    fix_en="Check DATABASE_URL, the PostgreSQL server and the connection pool."))

    try:
        import requests
        t0 = time.time()
        r = requests.get("https://fapi.binance.com/fapi/v1/time", timeout=6)
        t1 = time.time()
        server_ms = float(r.json()["serverTime"])
        drift = abs(server_ms - (t0 + t1) / 2 * 1000.0)
        out.append(_chk("svc.binance", "services", "pass", "high", "API Binance joignable", "Binance API reachable",
                        f"Latence {int((t1 - t0) * 1000)} ms", f"Latency {int((t1 - t0) * 1000)} ms"))
        if drift > 5000:
            st, sev = "fail", "high"
        elif drift > 1500:
            st, sev = "warn", "medium"
        else:
            st, sev = "pass", "info"
        out.append(_chk("svc.clock", "services", st, sev, "Horloge serveur synchronisée", "Server clock in sync",
                        f"Écart avec Binance : {int(drift)} ms", f"Offset vs Binance: {int(drift)} ms",
                        "Synchroniser l'horloge (NTP) : au-delà de quelques secondes Binance rejette les ordres signés (-1021).",
                        "Sync the clock (NTP): beyond a few seconds Binance rejects signed orders (-1021)."))
    except Exception as exc:  # noqa: BLE001
        out.append(_chk("svc.binance", "services", "fail", "high", "API Binance joignable", "Binance API reachable",
                        f"Échec : {type(exc).__name__}", f"Failed: {type(exc).__name__}",
                        "Vérifier la sortie réseau du serveur vers fapi.binance.com.",
                        "Check outbound network access to fapi.binance.com."))

    try:
        from database import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM optimization_jobs WHERE status = 'running' AND heartbeat_at < %s",
                            (time.time() - 300,))
                stale = int(cur.fetchone()[0])
        finally:
            conn.close()
        out.append(_chk("svc.optimizer", "services", "pass" if stale == 0 else "warn", "medium",
                        "Workers d'optimisation actifs", "Optimization workers healthy",
                        f"{stale} job(s) sans signe de vie depuis plus de 5 min" if stale else "",
                        f"{stale} job(s) with no heartbeat for over 5 min" if stale else "",
                        "Redémarrer le worker d'optimisation ; les jobs bloqués seront repris.",
                        "Restart the optimization worker; stuck jobs will be picked up again."))
    except Exception:  # noqa: BLE001
        out.append(_chk("svc.optimizer", "services", "skip", "info", "Workers d'optimisation", "Optimization workers",
                        "Contrôle indisponible (table absente ?)", "Check unavailable (table missing?)"))

    out.append(_chk("svc.telegram", "services", "pass" if os.getenv("TELEGRAM_TOKEN") else "warn", "low",
                    "Bot Telegram configuré", "Telegram bot configured",
                    fix_fr="Définir TELEGRAM_TOKEN pour recevoir les alertes de sécurité.",
                    fix_en="Set TELEGRAM_TOKEN to receive security alerts."))
    return out


# ---------------------------------------------------------------------------
# 2. Configuration
# ---------------------------------------------------------------------------
def check_configuration() -> List[dict]:
    import config
    out: List[dict] = []
    enc = getattr(config, "ENCRYPTION_KEY", "") or os.environ.get("ENCRYPTION_KEY", "")
    out.append(_chk("cfg.encryption", "configuration", "pass" if enc else "fail", "critical" if not enc else "info",
                    "Clé de chiffrement des clés API définie", "API-key encryption secret set",
                    fix_fr="Définir ENCRYPTION_KEY (secret long et aléatoire) : sans elle, les clés Binance ne sont pas protégées.",
                    fix_en="Set ENCRYPTION_KEY (long random secret): without it Binance keys are not protected."))
    if enc and len(str(enc)) < 32:
        out.append(_chk("cfg.encryption_len", "configuration", "warn", "medium", "Clé de chiffrement assez longue",
                        "Encryption secret long enough", fix_fr="Utiliser au moins 32 caractères aléatoires.",
                        fix_en="Use at least 32 random characters."))
    pw = str(getattr(config, "ADMIN_INITIAL_PASSWORD", "") or "")
    weak = (not pw) or len(pw) < 12 or pw.lower() in {"admin", "password", "changeme", "admin123", "bitsure"}
    out.append(_chk("cfg.admin_password", "configuration", "fail" if weak else "pass", "high",
                    "Mot de passe administrateur initial robuste", "Strong initial admin password",
                    fix_fr="Utiliser un mot de passe d'au moins 12 caractères et le changer après la première connexion.",
                    fix_en="Use at least 12 characters and change it after first sign-in."))
    origins = [str(o).strip() for o in (getattr(config, "ALLOWED_ORIGINS", None) or []) if o]
    bad = [o for o in origins if o == "*" or (o.startswith("http://") and "localhost" not in o and "127.0.0.1" not in o)]
    out.append(_chk("cfg.cors_origins", "configuration", "fail" if bad else "pass", "medium",
                    "Origines CORS autorisées restreintes", "Allowed CORS origins restricted",
                    f"{len(bad)} origine(s) trop permissive(s)" if bad else "",
                    f"{len(bad)} overly permissive origin(s)" if bad else "",
                    "Limiter ALLOWED_ORIGINS à vos domaines https.", "Restrict ALLOWED_ORIGINS to your https domains."))
    app_url = str(getattr(config, "APP_URL", "") or "")
    out.append(_chk("cfg.https", "configuration", "pass" if app_url.startswith("https://") else "warn", "medium",
                    "Application servie en HTTPS", "Application served over HTTPS",
                    "Les cookies de session ne reçoivent l'attribut Secure qu'en HTTPS.",
                    "Session cookies only get the Secure flag over HTTPS.",
                    "Définir APP_URL en https://…", "Set APP_URL to https://…"))
    debug_on = os.getenv("DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    out.append(_chk("cfg.debug", "configuration", "fail" if debug_on else "pass", "medium",
                    "Mode debug désactivé", "Debug mode off",
                    fix_fr="Retirer la variable DEBUG en production.", fix_en="Remove DEBUG in production."))
    try:
        server_src = (ROOT / "web_api_server.py").read_text(encoding="utf-8")
        out.append(_chk("cfg.rate_limit", "configuration", "pass" if "Trop de tentatives" in server_src else "warn", "high",
                        "Limitation des tentatives de connexion", "Login attempt rate limiting",
                        fix_fr="Réactiver la limitation des tentatives de connexion.",
                        fix_en="Re-enable login attempt rate limiting."))
    except OSError:
        pass
    env_file = ROOT / ".env"
    out.append(_chk("cfg.env_file", "configuration", "warn" if env_file.exists() else "pass", "medium",
                    "Pas de fichier .env dans l'application", "No .env file inside the application",
                    "Un .env déployé avec le code peut fuiter ; préférez les variables d'environnement de l'hébergeur.",
                    "A .env shipped with the code can leak; prefer the host's environment variables.",
                    "Supprimer .env du déploiement et l'exclure du dépôt (.gitignore).",
                    "Remove .env from the deployment and exclude it from the repository (.gitignore)."))
    return out


# ---------------------------------------------------------------------------
# 3. En-têtes HTTP et CORS (sonde réelle)
# ---------------------------------------------------------------------------
def check_headers() -> List[dict]:
    out: List[dict] = []
    try:
        status, h = _probe("GET", "/api/health", {"X-Forwarded-Proto": "https", "Origin": "https://evil.example"})
    except Exception as exc:  # noqa: BLE001
        return [_chk("hdr.probe", "headers", "skip", "info", "Sonde des en-têtes HTTP", "HTTP headers probe",
                     f"Sonde locale impossible : {type(exc).__name__}", f"Local probe failed: {type(exc).__name__}")]
    required = {
        "x-content-type-options": ("nosniff", "X-Content-Type-Options: nosniff"),
        "x-frame-options": (None, "X-Frame-Options"),
        "referrer-policy": (None, "Referrer-Policy"),
        "strict-transport-security": (None, "Strict-Transport-Security (HSTS)"),
    }
    for key, (value, label) in required.items():
        present = key in h and (value is None or h[key].lower() == value)
        out.append(_chk(f"hdr.{key}", "headers", "pass" if present else "fail", "medium", f"En-tête {label}", f"Header {label}",
                        fix_fr=f"Ajouter l'en-tête {label} à toutes les réponses.", fix_en=f"Add the {label} header to all responses."))
    out.append(_chk("hdr.csp", "headers", "pass" if "content-security-policy" in h else "info", "low",
                    "Content-Security-Policy", "Content-Security-Policy",
                    "Absente : recommandée contre l'injection de scripts (XSS).", "Missing: recommended against script injection (XSS).",
                    "Introduire une CSP en mode « report-only » d'abord pour ne rien casser.",
                    "Introduce a CSP in report-only mode first so nothing breaks."))
    server_hdr = h.get("server", "")
    leaks = bool(re.search(r"python|basehttp|werkzeug", server_hdr, re.I))
    out.append(_chk("hdr.server", "headers", "fail" if leaks else "pass", "low",
                    "Version du serveur non divulguée", "Server version not disclosed",
                    f"En-tête Server : {server_hdr}" if leaks else "", f"Server header: {server_hdr}" if leaks else "",
                    "Masquer la version dans l'en-tête Server.", "Hide the version in the Server header."))
    acao, acac = h.get("access-control-allow-origin", ""), h.get("access-control-allow-credentials", "").lower()
    reflected = acao in ("https://evil.example", "*") and (acac == "true" or acao == "https://evil.example")
    out.append(_chk("hdr.cors", "headers", "fail" if reflected else "pass", "critical",
                    "CORS : une origine étrangère n'est pas autorisée", "CORS: foreign origins are not allowed",
                    f"Access-Control-Allow-Origin = {acao}" if reflected else "",
                    f"Access-Control-Allow-Origin = {acao}" if reflected else "",
                    "Ne refléter que les origines de ALLOWED_ORIGINS.", "Only reflect origins listed in ALLOWED_ORIGINS.",
                    auto_lock=True))
    return out


# ---------------------------------------------------------------------------
# 4. Routes
# ---------------------------------------------------------------------------
def _route_literals(test: ast.AST) -> List[str]:
    found: List[str] = []
    for n in ast.walk(test):
        if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == "path":
            for op, c in zip(n.ops, n.comparators):
                if isinstance(op, ast.Eq) and isinstance(c, ast.Constant) and isinstance(c.value, str):
                    found.append(c.value)
                elif isinstance(op, ast.In) and isinstance(c, (ast.Tuple, ast.List, ast.Set)):
                    found += [e.value for e in c.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return found


def analyse_routes(source: str) -> Dict[str, Any]:
    """Analyse statique de do_GET / do_POST : routes avant la porte d'authentification = publiques."""
    tree = ast.parse(source)
    result: Dict[str, Any] = {"public": {"GET": set(), "POST": set()}, "protected": {"GET": set(), "POST": set()}, "gate_found": {}}
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        for fn in cls.body:
            if not (isinstance(fn, ast.FunctionDef) and fn.name in ("do_GET", "do_POST")):
                continue
            method = "GET" if fn.name == "do_GET" else "POST"
            route_ifs = [n for n in ast.walk(fn) if isinstance(n, ast.If) and _route_literals(n.test)]
            inside_route: set = set()
            for rif in route_ifs:
                for sub in ast.walk(rif):
                    inside_route.add(id(sub))
            gate_line = None
            for n in ast.walk(fn):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_require_auth"
                        and id(n) not in inside_route):
                    gate_line = n.lineno if gate_line is None else min(gate_line, n.lineno)
            result["gate_found"][method] = gate_line is not None
            if gate_line is None:
                continue
            for rif in route_ifs:
                bucket = "public" if rif.lineno < gate_line else "protected"
                for lit in _route_literals(rif.test):
                    if lit.startswith("/"):
                        result[bucket][method].add(lit)
        # Tables de dispatch « chemin -> méthode » (ex. _handle_auth_extension_post) : chaque méthode est publique
        # si elle n'appelle pas _require_auth elle-même.
        methods = {f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)}
        for f in cls.body:
            if not isinstance(f, ast.FunctionDef):
                continue
            for d in [n for n in ast.walk(f) if isinstance(n, ast.Dict)]:
                for k, v in zip(d.keys, d.values):
                    if (isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value.startswith("/api/")
                            and isinstance(v, ast.Attribute) and v.attr in methods):
                        guarded = any(isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "_require_auth"
                                      for x in ast.walk(methods[v.attr]))
                        method = "POST" if f.name.endswith("_post") else "GET"
                        result["protected" if guarded else "public"][method].add(k.value)
    return result


def check_routes(progress: Optional[Callable[[int, int], None]] = None) -> List[dict]:
    out: List[dict] = []
    try:
        analysis = analyse_routes((ROOT / "web_api_server.py").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [_chk("rte.analysis", "routes", "skip", "info", "Analyse des routes", "Route analysis",
                     f"Impossible : {type(exc).__name__}", f"Unable: {type(exc).__name__}")]
    if not all(analysis["gate_found"].get(m) for m in ("GET", "POST")):
        out.append(_chk("rte.gate", "routes", "fail", "critical", "Porte d'authentification globale détectée",
                        "Global authentication gate detected",
                        "La structure du serveur a changé : impossible de prouver que les routes sont protégées.",
                        "The server structure changed: cannot prove routes are protected.",
                        "Remettre une porte d'authentification unique avant les routes privées.",
                        "Restore a single authentication gate before private routes."))
        return out

    # a) routes publiques inattendues
    unexpected = []
    for method in ("GET", "POST"):
        for route in sorted(analysis["public"][method]):
            if route not in EXPECTED_PUBLIC[method] and not route.endswith("*") and route not in ("/api", "/assets/"):
                unexpected.append(f"{method} {route}")
    out.append(_chk("rte.unexpected_public", "routes", "fail" if unexpected else "pass", "high",
                    "Aucune route publique inattendue", "No unexpected public route",
                    ", ".join(unexpected) if unexpected else "", ", ".join(unexpected) if unexpected else "",
                    "Placer ces routes derrière la porte d'authentification, ou les ajouter à EXPECTED_PUBLIC si elles sont voulues.",
                    "Put these routes behind the authentication gate, or add them to EXPECTED_PUBLIC if intended."))

    # b) sonde anonyme de chaque route protégée
    targets = [(m, r) for m in ("GET", "POST") for r in sorted(analysis["protected"][m])
               if "*" not in r and not r.endswith("/") ]
    targets += sorted(SELF_AUTH_PUBLIC)
    leaks, soft, probed, skipped = [], [], 0, 0
    for i, (method, route) in enumerate(targets):
        if progress:
            progress(i, len(targets))
        try:
            status, _ = _probe(method, route, body=b"{}" if method == "POST" else None)
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        probed += 1
        if status in (401, 403):
            pass
        elif status in (404, 405, 429):
            skipped += 1
        elif 200 <= status < 300:
            leaks.append(f"{method} {route} → {status}")
        else:
            soft.append(f"{method} {route} → {status}")
        time.sleep(0.02)
    out.append(_chk("rte.anonymous_access", "routes", "fail" if leaks else "pass", "critical",
                    "Les routes privées refusent les appels anonymes", "Private routes reject anonymous calls",
                    "; ".join(leaks[:15]) if leaks else f"{probed} routes sondées sans connexion",
                    "; ".join(leaks[:15]) if leaks else f"{probed} routes probed without sign-in",
                    "Protéger immédiatement ces routes (authentification requise).", "Protect these routes immediately (authentication required).",
                    auto_lock=True))
    if soft:
        out.append(_chk("rte.pre_auth_logic", "routes", "warn", "medium",
                        "Aucune route ne traite la requête avant l'authentification", "No route processes input before authentication",
                        "; ".join(soft[:15]), "; ".join(soft[:15]),
                        "Vérifier l'authentification avant toute validation ou lecture de données.",
                        "Check authentication before any validation or data access."))
    if skipped:
        out.append(_chk("rte.skipped", "routes", "info", "info", "Routes non sondées", "Routes not probed",
                        f"{skipped} route(s) ignorée(s) (404/405/429/erreur réseau)", f"{skipped} route(s) skipped (404/405/429/network error)"))
    return out


# ---------------------------------------------------------------------------
# 5. Clés Binance des utilisateurs
# ---------------------------------------------------------------------------
def check_binance_keys(max_users: int = 200) -> List[dict]:
    try:
        from database import get_connection
        import crypto_utils
        from binance_manager import check_api_key_permissions
        from trading_config import get_binance_credentials
    except Exception as exc:  # noqa: BLE001
        return [_chk("key.module", "binance_keys", "skip", "info", "Contrôle des clés Binance", "Binance keys check",
                     f"Indisponible : {type(exc).__name__}", f"Unavailable: {type(exc).__name__}")]
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT user_id FROM binance_credentials LIMIT %s", (max_users,))
                users = [int(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return [_chk("key.list", "binance_keys", "skip", "info", "Contrôle des clés Binance", "Binance keys check",
                     f"Liste des comptes indisponible : {type(exc).__name__}", f"Account list unavailable: {type(exc).__name__}")]
    undecryptable, withdraw, checked = [], [], 0
    for uid in users:
        creds = None
        for market in ("futures", "spot"):
            try:
                creds = get_binance_credentials(uid, market_type=market)
            except Exception:  # noqa: BLE001
                creds = None
            if creds:
                break
        if not creds:
            undecryptable.append(uid)
            continue
        if creds.get("testnet"):
            continue  # pas de permissions vérifiables sur le testnet
        try:
            check_api_key_permissions(creds["api_key"], creds["api_secret"], testnet=False)
            checked += 1
        except Exception as exc:  # noqa: BLE001
            if "retrait" in str(exc).lower() or "withdraw" in str(exc).lower():
                withdraw.append(uid)
        time.sleep(0.3)
    return [
        _chk("key.decrypt", "binance_keys", "fail" if undecryptable else "pass", "medium",
             "Clés Binance stockées lisibles", "Stored Binance keys readable",
             f"{len(undecryptable)} compte(s) : {undecryptable[:10]}" if undecryptable else f"{len(users)} compte(s) contrôlé(s)",
             f"{len(undecryptable)} account(s): {undecryptable[:10]}" if undecryptable else f"{len(users)} account(s) checked",
             "Demander à ces utilisateurs de ressaisir leurs clés (clé de chiffrement changée ou données corrompues).",
             "Ask these users to re-enter their keys (encryption secret changed or corrupted data)."),
        _chk("key.withdrawals", "binance_keys", "fail" if withdraw else "pass", "high",
             "Aucune clé réelle avec droit de retrait", "No live key with withdrawal permission",
             f"Comptes concernés : {withdraw[:10]}" if withdraw else f"{checked} clé(s) réelle(s) contrôlée(s)",
             f"Affected accounts: {withdraw[:10]}" if withdraw else f"{checked} live key(s) checked",
             "Demander à ces utilisateurs de désactiver les retraits sur leur clé Binance.",
             "Ask these users to disable withdrawals on their Binance key."),
    ]


# ---------------------------------------------------------------------------
# 6. Code : secrets oubliés, dépendances
# ---------------------------------------------------------------------------
_SKIP_DIRS = {"node_modules", ".git", "dist", "tests", "__pycache__", ".venv", "venv", "build"}
_SKIP_FILES = {"web_frontend_bundle_data.py", "package-lock.json", "trading.log"}
_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"""(?i)(?:getenv|environ\.get)\(\s*["'][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*["']\s*,\s*["']([A-Za-z0-9_\-/+=]{24,})["']"""),
    re.compile(r"""(?i)\b(?:api[_-]?key|api[_-]?secret|secret|token|passw(?:or)?d)\w*\s*[:=]\s*["']([A-Za-z0-9_\-/+=]{32,})["']"""),
]
_PLACEHOLDER = re.compile(r"(?i)(x{4,}|your|example|changeme|placeholder|fake|dummy|test|sample|0{6,}|<)")


def scan_secrets(root: Path = ROOT, max_files: int = 4000) -> List[str]:
    hits: List[str] = []
    n = 0
    for path in root.rglob("*"):
        if n > max_files:
            break
        if not path.is_file() or any(p in _SKIP_DIRS for p in path.relative_to(root).parts) or path.name in _SKIP_FILES:
            continue
        if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".sh"} \
                and not path.name.startswith(".env"):
            continue
        try:
            if path.stat().st_size > 1_500_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        n += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in _SECRET_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                value = m.group(1) if m.groups() else ""
                if value and (_PLACEHOLDER.search(value) or len(set(value)) < 6):
                    continue
                if path.name == ".env.example":
                    continue
                hits.append(f"{path.relative_to(root)}:{lineno}")
                break
    return hits


def check_code() -> List[dict]:
    out: List[dict] = []
    hits = scan_secrets()
    out.append(_chk("code.secrets", "code", "fail" if hits else "pass", "high",
                    "Aucun secret écrit dans le code", "No secret written in the code",
                    f"{len(hits)} emplacement(s) suspect(s) : {', '.join(hits[:10])}" if hits else "",
                    f"{len(hits)} suspicious location(s): {', '.join(hits[:10])}" if hits else "",
                    "Retirer ces valeurs du code, les régénérer chez le fournisseur et les passer en variables d'environnement.",
                    "Remove these values from the code, regenerate them at the provider and move them to environment variables."))
    req = ROOT / "requirements.txt"
    if req.exists():
        loose = [l.strip() for l in req.read_text(encoding="utf-8", errors="ignore").splitlines()
                 if l.strip() and not l.startswith("#") and "==" not in l and not l.startswith("-")]
        out.append(_chk("code.pinning", "code", "warn" if loose else "pass", "low",
                        "Dépendances Python figées", "Python dependencies pinned",
                        f"{len(loose)} non figée(s) : {', '.join(loose[:8])}" if loose else "",
                        f"{len(loose)} unpinned: {', '.join(loose[:8])}" if loose else "",
                        "Figer les versions (==) pour des déploiements reproductibles.", "Pin versions (==) for reproducible deployments."))
    try:
        proc = subprocess.run([sys.executable, "-m", "pip_audit", "-r", str(req), "--progress-spinner", "off", "-f", "json"],
                              capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        if proc.returncode in (0, 1) and proc.stdout.strip().startswith(("{", "[")):
            data = json.loads(proc.stdout)
            deps = data.get("dependencies", data) if isinstance(data, dict) else data
            vulnerable = [d.get("name") for d in deps if isinstance(d, dict) and d.get("vulns")]
            out.append(_chk("code.vulns", "code", "fail" if vulnerable else "pass", "high",
                            "Aucune vulnérabilité connue dans les dépendances", "No known vulnerability in dependencies",
                            ", ".join(map(str, vulnerable[:10])) if vulnerable else "", ", ".join(map(str, vulnerable[:10])) if vulnerable else "",
                            "Mettre à jour ces paquets.", "Update these packages."))
        else:
            raise RuntimeError("pip-audit indisponible")
    except Exception:  # noqa: BLE001
        out.append(_chk("code.vulns", "code", "skip", "info", "Vulnérabilités des dépendances", "Dependency vulnerabilities",
                        "Non vérifié : installer pip-audit (pip install pip-audit) pour activer ce contrôle.",
                        "Not checked: install pip-audit (pip install pip-audit) to enable this check."))
    return out


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------
def build_report(checks: List[dict], started: float, finished: float, trigger: str) -> dict:
    counts = {s: 0 for s in SEVERITIES}
    passed = 0
    for c in checks:
        if c["status"] == "pass":
            passed += 1
        elif c["status"] in ("fail", "warn"):
            counts[c["severity"]] = counts.get(c["severity"], 0) + 1
    failing = [c for c in checks if c["status"] == "fail"]
    if any(c["severity"] == "critical" for c in failing):
        overall = "critical"
    elif any(c["severity"] == "high" for c in failing):
        overall = "degraded"
    elif counts["critical"] + counts["high"] + counts["medium"] + counts["low"]:
        overall = "attention"
    else:
        overall = "ok"
    return {
        "started_at": started, "finished_at": finished, "duration_s": round(finished - started, 1), "trigger": trigger,
        "overall": overall, "counts": counts, "passed": passed, "total": len(checks), "checks": checks,
        "disclaimer_fr": "Contrôles de configuration réussis ne signifie pas « site sécurisé » : cet audit ne remplace pas un audit de code ni un test d'intrusion externe.",
        "disclaimer_en": "Passing configuration checks does not mean “site secured”: this audit does not replace a code review or an external penetration test.",
    }


def _finding_keys(report: Optional[dict]) -> set:
    if not report:
        return set()
    return {c["id"] for c in report["checks"] if c["status"] == "fail" and c["severity"] in ("critical", "high")}


def _persist(report: dict) -> None:
    try:
        from database import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS security_audit_reports (id SERIAL PRIMARY KEY, created_at DOUBLE PRECISION, "
                            "overall TEXT, report_json TEXT)")
                cur.execute("INSERT INTO security_audit_reports (created_at, overall, report_json) VALUES (%s, %s, %s)",
                            (report["finished_at"], report["overall"], json.dumps(report)))
                cur.execute("DELETE FROM security_audit_reports WHERE id NOT IN (SELECT id FROM security_audit_reports ORDER BY id DESC LIMIT 50)")
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit: persistance impossible: %s", exc)


def _load_persisted() -> None:
    try:
        from database import get_connection
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT report_json FROM security_audit_reports ORDER BY id DESC LIMIT 20")
                rows = [json.loads(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()
        for rep in reversed(rows):
            _state["history"].append(_summary(rep))
        if rows and not _state["last"]:
            _state["last"] = rows[0]
    except Exception:  # noqa: BLE001
        pass


def _summary(report: dict) -> dict:
    return {k: report[k] for k in ("finished_at", "duration_s", "overall", "counts", "passed", "total", "trigger")}


def _react(report: dict, previous: Optional[dict]) -> None:
    """Alerte l'admin sur les nouveaux problèmes graves ; verrouille l'AutoTrade si un problème critique l'exige."""
    new = _finding_keys(report) - _finding_keys(previous)
    lock_ids = sorted(c["id"] for c in report["checks"] if c["auto_lock"])
    actions: dict = {}
    try:
        from config import ADMIN_ID
        from trading_safety import _dispatch_or_queue_notification, engage_safe_mode
    except Exception:  # noqa: BLE001
        report["actions"] = actions
        return
    if lock_ids and AUTO_LOCK and _state["last_lock_signature"] != lock_ids:
        users: List[int] = []
        try:
            from database import get_connection
            conn = get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT user_id FROM trading_config WHERE auto_trade = TRUE")
                    users = [int(r[0]) for r in cur.fetchall()]
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("audit: impossible de lister les AutoTrade actifs: %s", exc)
        for uid in users:
            try:
                engage_safe_mode(uid, f"Audit de sécurité : problème critique ({', '.join(lock_ids)})", disable_autotrade=True)
            except Exception as exc:  # noqa: BLE001
                logger.error("audit: verrouillage impossible user=%s: %s", uid, exc)
        _state["last_lock_signature"] = lock_ids
        actions["auto_lock"] = {"users": len(users), "findings": lock_ids}
    if new and ADMIN_ID:
        titles = [c["title_fr"] for c in report["checks"] if c["id"] in new]
        text = "🔐 Audit de sécurité Bitsure : nouveau(x) problème(s) grave(s)\n- " + "\n- ".join(titles[:8])
        if actions.get("auto_lock"):
            text += f"\n\nAutoTrade désactivé pour {actions['auto_lock']['users']} utilisateur(s) (mode sécurité)."
        try:
            _dispatch_or_queue_notification(int(ADMIN_ID), text)
        except Exception as exc:  # noqa: BLE001
            logger.error("audit: notification admin impossible: %s", exc)
    if not lock_ids:
        _state["last_lock_signature"] = None
    report["actions"] = actions


def run_audit(trigger: str = "manual") -> Optional[dict]:
    if not _lock.acquire(blocking=False):
        return None  # un audit est déjà en cours
    try:
        _state["running"] = True
        started = time.time()
        steps: List[tuple] = [
            ("Services", "Services", check_services),
            ("Configuration", "Configuration", check_configuration),
            ("En-têtes HTTP et CORS", "HTTP headers and CORS", check_headers),
            ("Protection des routes", "Route protection", check_routes),
            ("Clés Binance des utilisateurs", "Users' Binance keys", check_binance_keys),
            ("Code et dépendances", "Code and dependencies", check_code),
        ]
        checks: List[dict] = []
        for i, (fr, en, fn) in enumerate(steps):
            _set_progress(i, len(steps), fr, en)
            try:
                checks += fn()
            except Exception as exc:  # noqa: BLE001
                logger.exception("audit: étape %s en échec", fr)
                checks.append(_chk(f"audit.step.{i}", "audit", "warn", "medium", f"Étape « {fr} » interrompue",
                                   f"Step “{en}” interrupted", type(exc).__name__, type(exc).__name__))
        report = build_report(checks, started, time.time(), trigger)
        previous = _state["last"]
        _react(report, previous)
        _state["last"] = report
        _state["history"].append(_summary(report))
        _persist(report)
        logger.info("audit: terminé en %.1fs overall=%s %s", report["duration_s"], report["overall"], report["counts"])
        return report
    finally:
        _state["running"] = False
        _state["progress"] = None
        _lock.release()


def start_background(port: Optional[int] = None) -> None:
    """Lance l'audit 8 s après le démarrage, puis à intervalle régulier (SECURITY_AUDIT_INTERVAL_HOURS)."""
    configure(port)
    if not ENABLED or _state["started"]:
        return
    _state["started"] = True

    def loop() -> None:
        _load_persisted()
        time.sleep(8)
        while True:
            try:
                run_audit("startup" if _state["last"] is None else "scheduled")
            except Exception:  # noqa: BLE001
                logger.exception("audit: échec de l'exécution planifiée")
            time.sleep(max(INTERVAL_HOURS, 0.25) * 3600)

    threading.Thread(target=loop, name="bitsure-security-audit", daemon=True).start()


def run_async(trigger: str = "manual") -> bool:
    """Démarre un audit en arrière-plan. False si un audit est déjà en cours."""
    if _state["running"]:
        return False
    threading.Thread(target=run_audit, args=(trigger,), name="bitsure-security-audit-manual", daemon=True).start()
    return True


def get_state() -> dict:
    """État complet pour l'administrateur."""
    return {
        "enabled": ENABLED, "running": bool(_state["running"]), "progress": _state["progress"],
        "last": _state["last"], "history": list(_state["history"]), "interval_hours": INTERVAL_HOURS,
        "auto_lock": AUTO_LOCK,
    }


def public_status() -> str:
    """Résumé destiné à tous les utilisateurs : operational | degraded | checking. Aucun détail technique."""
    last = _state["last"]
    if last is None:
        return "checking" if (_state["running"] and ENABLED) else "operational"
    # « Dégradé » = un SERVICE est réellement en panne (base de données, Binance, horloge...). Les constats de
    # configuration, de code, d'en-têtes ou de clés sont des tâches pour l'admin : ils ne doivent jamais afficher
    # « service dégradé » à tous les utilisateurs.
    service_failure = any(
        c.get("category") == "services" and c.get("status") == "fail" and c.get("severity") in ("critical", "high")
        for c in last.get("checks", [])
    )
    return "degraded" if service_failure else "operational"
