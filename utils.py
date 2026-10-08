import hashlib
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


import re

# ---------------------------------------------------------------------------
# SYMBOL NORMALIZATION — single source of truth for every Binance code path
# ---------------------------------------------------------------------------
#
# All user-facing symbols must pass through normalize_symbol() before hitting
# analysis, storage, signal confirmation, AutoTrade, Live Trading or any
# Binance API call.
#
# Rules applied in order:
#   1. Strip surrounding whitespace, convert to UPPERCASE
#   2. Remove separators: spaces, slashes, dashes, underscores
#   3. Map common USD-denominated base assets to their USDT Binance ticker
#      (BTC → BTCUSDT, ETH → ETHUSDT, etc.)
#   4. Reject symbols that are still not alphanumeric after the above steps
#
# Examples:
#   "BTC/USDT" → "BTCUSDT"
#   "BTC-USDT" → "BTCUSDT"
#   "btcusdt"  → "BTCUSDT"
#   "ETHUSDT"  → "ETHUSDT"   (already canonical, no-op)
#   "XAU/USD"  → "XAUUSD"
# ---------------------------------------------------------------------------

# Separator characters to strip before comparing tokens
_SEPARATOR_RE = re.compile(r"[\s/\-_]+")


# Suffixes de contrats perpétuels ou futures à nettoyer avant normalisation
_PERP_SUFFIX_RE = re.compile(r"(?:PERP|SWAP|FUTURES|FUT|[_\-]\d{6})$", re.IGNORECASE)


def normalize_symbol(symbol: str) -> str:
    """Convertit une chaîne de symbole fournie par l'utilisateur ou un flux externe
    en un ticker standardisé compatible Binance (ex: 'BTC/USDT', 'btcusdt_perp' -> 'BTCUSDT').

    Lève ValueError avec un message clair si le résultat reste invalide après
    toutes les étapes de nettoyage.
    """
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Le symbole ne peut pas être vide.")

    # Étape 1 — Majuscules et suppression des espaces englobants
    s = symbol.strip().upper()

    # Étape 2 — Nettoyage des suffixes de type contrat (:USDT, _PERP, -PERP, etc.)
    if ":" in s:
        s = s.split(":", 1)[0]

    # Étape 3 — Suppression des séparateurs (espaces, /, -, _)
    s = _SEPARATOR_RE.sub("", s)

    # Étape 4 — Suppression des suffixes PERP / SWAP / FUTURES collés
    s = _PERP_SUFFIX_RE.sub("", s)

    # Étape 5 — Conversion des alias courts vers les symboles officiellement documentés (BTCUSDT, ETHUSDT, XAUUSD)
    if s in ("BTC", "XBT"):
        s = "BTCUSDT"
    elif s == "ETH":
        s = "ETHUSDT"
    elif s == "XAU":
        s = "XAUUSD"

    # Étape 6 — Vérification stricte : seuls les symboles documentés dans le bot sont autorisés
    from config import DOCUMENTED_SYMBOLS
    if s not in DOCUMENTED_SYMBOLS:
        raise ValueError(
            f"Symbole non supporté : « {symbol} ». "
            f"Seuls les symboles documentés dans le bot sont autorisés : {', '.join(DOCUMENTED_SYMBOLS)}."
        )

    return s


def is_valid_symbol(symbol: str) -> bool:
    """Return True only if symbol passes normalize_symbol without error."""
    try:
        normalize_symbol(symbol)
        return True
    except ValueError:
        return False


def format_number(num: float, decimals: int = 2) -> str:
    """Formate un nombre avec séparateur de milliers."""
    if abs(num) < 0.01 and num != 0:
        return f"{num:.8f}".rstrip('0').rstrip('.')
    # Pour le Forex, on veut souvent 4 décimales
    if 0.01 <= abs(num) < 1000:
        decimals = max(decimals, 4)
    return f"{num:,.{decimals}f}"


def format_timestamp(ts: float) -> str:
    """Convertit timestamp en date lisible"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def get_date_days_ago(days: int) -> datetime:
    """Retourne la date il y a N jours"""
    return datetime.now() - timedelta(days=days)


def escape_markdown(text: str) -> str:
    """Escapes characters that have special meaning in Telegram Markdown."""
    res = str(text)
    for char in ["_", "*", "`", "["]:
        res = res.replace(char, f"\\{char}")
    return res


def cache_key(*args) -> str:
    """Génère une clé de cache unique"""
    raw = "|".join(str(a) for a in args)
    return hashlib.md5(raw.encode()).hexdigest()
