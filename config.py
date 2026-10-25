import os

# =========================================================
# 1. LES SEULES VARIABLES À ENREGISTRER SUR RENDER / .ENV
# =========================================================
# Tu n'as besoin de configurer que ces 3 variables (et éventuellement TWELVEDATA_API_KEY) :
# - TELEGRAM_TOKEN
# - ADMIN_ID
# - DATABASE_URL

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

_raw_admin_id = os.environ.get("ADMIN_ID", "").strip()
try:
    ADMIN_ID = int(_raw_admin_id) if _raw_admin_id else 0
except ValueError:
    ADMIN_ID = 0

if ADMIN_ID == 0:
    import logging as _cfg_logging
    _cfg_logging.getLogger(__name__).warning(
        "⚠️ ADMIN_ID == 0 : aucun identifiant Telegram administrateur numérique configuré (définissez ADMIN_ID=<id_numérique>)."
    )

ADMIN_USERNAME = "@btsrteddy"

DATABASE_URL = os.environ.get("DATABASE_URL")

# Optionnel (uniquement si tu analyses Forex hors Binance ou reçois des paiements Binance Pay)
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
BINANCE_ID = os.environ.get("BINANCE_ID", "")

# Optionnel : Clé API Gemini pour l'interpréteur de logs (/logs)
# Utilise par défaut gemini-3.1-flash-lite (ultra-rapide et très économe en tokens).
# Si vide, l'interpréteur de logs fonctionne quand même à 100% grâce à son moteur de diagnostic local (0 token).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_LOG_MODEL = os.environ.get("GEMINI_LOG_MODEL", "gemini-3.1-flash-lite")

# =========================================================
# 1B. AUTHENTIFICATION WEB, INITIALISATION ADMIN & GOOGLE OAUTH
# =========================================================
# Identité explicite de l'administrateur initial du site Web (ne jamais attribuer au 1er visiteur)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD", "").strip()
SESSION_SECRET = os.environ.get("SESSION_SECRET", "").strip()
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "").strip()

# Google OAuth 2.0 (Optionnel)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
APP_URL = os.environ.get("APP_URL", "").strip().rstrip("/")
ALLOWED_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
if APP_URL and APP_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(APP_URL)

# Quotas journaliers par défaut pour les nouveaux comptes Web approuvés
DEFAULT_DAILY_ANALYSIS_LIMIT = int(os.environ.get("DEFAULT_DAILY_ANALYSIS_LIMIT", "15"))
DEFAULT_DAILY_SCAN_LIMIT = int(os.environ.get("DEFAULT_DAILY_SCAN_LIMIT", "10"))
DEFAULT_MAX_ALERTS_LIMIT = int(os.environ.get("DEFAULT_MAX_ALERTS_LIMIT", "10"))
DEFAULT_MAX_PAPER_TRADES_LIMIT = int(os.environ.get("DEFAULT_MAX_PAPER_TRADES_LIMIT", "25"))

# =========================================================
# 2. CONFIGURATION PAR DÉFAUT AUTOTRADE & SÉCURITÉ
# (Tout est géré ici directement en Python, aucune variable Render requise)
# =========================================================

# Mode Testnet par défaut (False = Argent réel sur Binance, True = Testnet)
BINANCE_TESTNET = True

# SÉCURITÉ : plus aucune clé Binance par défaut. Chaque compte utilise UNIQUEMENT ses propres clés
# (table binance_credentials). Ces constantes restent vides et ne sont plus utilisées comme repli pour
# les utilisateurs : un compte sans clés n'a pas accès à Binance (testnet ou live).
DEFAULT_BINANCE_TESTNET_API_KEY = ""
DEFAULT_BINANCE_TESTNET_API_SECRET = ""
DEFAULT_BINANCE_SPOT_TESTNET_API_KEY = ""
DEFAULT_BINANCE_SPOT_TESTNET_API_SECRET = ""

# Symboles officiellement documentés dans le bot (aucun autre symbole ne doit apparaître ni être analysé en analyse périodique)
# SOURCE DE VÉRITÉ UNIQUE de l'univers : toute liste de symboles du projet doit dériver de ces constantes.
# Marchés crypto Binance (Spot + USD-M Futures). Ajouter un symbole = l'ajouter ICI (+ éventuellement un override
# dans SYMBOL_PARAM_OVERRIDES plus bas), pas dans d'autres fichiers.
BINANCE_CRYPTO_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "BNBUSDT",
    "ZECUSDT",
)
# Or (perpétuel TradFi, Futures uniquement) : conserve son propre flux.
DOCUMENTED_SYMBOLS = BINANCE_CRYPTO_SYMBOLS + ("XAUUSDT",)

# Fragment SQL « 'A', 'B', ... » généré depuis l'univers (valeurs issues du code uniquement, jamais d'une saisie utilisateur).
DOCUMENTED_SYMBOLS_SQL = ", ".join("'%s'" % _s for _s in DOCUMENTED_SYMBOLS)

# Symboles autorisés à utiliser les REPLIS historiques (filtres Binance lot/tick de secours, données locales de secours)
# quand l'API est injoignable. Les nouveaux symboles n'y figurent PAS volontairement : un tick/step ou des bougies
# inventés seraient faux (DOGE/XRP/ADA ont des ticks très fins) -> on refuse l'ordre / on renvoie WAIT plutôt que
# d'agir sur des données erronées.
LEGACY_FALLBACK_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "XAUUSDT"})

# Symboles qui n'existent que sur Binance USD-M Futures (pas de marché Spot) : TradFi Perpetual (or).
# Leurs prix/historiques doivent être lus sur /fapi, jamais sur /api/v3.
FUTURES_ONLY_SYMBOLS = frozenset({"XAUUSDT"})

# Paramètres par défaut d'un profil de trading (optimisés haute sélectivité : gagner plus, perdre moins)
AUTO_TRADE_DEFAULT = False
PERIODIC_ANALYSIS_DEFAULT = False
DEFAULT_MARKET_TYPE = "futures"          # "futures" ou "spot"
DEFAULT_TRADING_STYLE = "day"            # "scalping", "scalping_15m", "day", "swing", "position"
DEFAULT_ANALYSIS_TIMEFRAME = "1h"        # "5m", "15m", "1h", "4h", "1d"
DEFAULT_ANALYSIS_INTERVAL_MINUTES = 5    # 5 ou 10 minutes
DEFAULT_LEVERAGE = 1                     # Levier x1 par défaut
DEFAULT_RISK_PER_TRADE = 1.0             # 1.0% du capital risqué par trade
DEFAULT_MAX_POSITIONS = 2                # Max 2 positions simultanées pour concentrer sur les meilleurs setups
DEFAULT_MIN_SCORE = 68                   # Score Teddy minimum calibré par walk-forward (68/100 + MTF + ADX rising)
DEFAULT_MAX_DAILY_LOSS = 3.0             # Perte journalière max réduite à 3% pour couper les mauvaises journées tôt
DEFAULT_TRAILING_STOP = True             # Trailing stop activé par défaut pour sécuriser les gains
DEFAULT_DCA_ENABLED = False

# Plafonds de risque et délais de sécurité
MAX_POSITION_EXPOSURE_PCT = 50.0         # Exposition max par position (50% du capital)
SIGNAL_VALIDITY_SECONDS = 900            # Validité d'un signal (15 minutes)
DEFAULT_SAFETY_LOCK_TTL_SECONDS = 3600   # Délai avant envoi d'un rappel unique si safety_lock reste actif (1h / 3600s)

# Pool PostgreSQL
DB_POOL_MINCONN = 1
DB_POOL_MAXCONN = 10

# =========================================================
# 3. ACCÈS & UTILISATEURS
# =========================================================

ACCESS_MODE = "approved_only"
ALLOW_AUTO_REGISTER = True
TRIAL_DAYS = 14
PLAN_DURATION_DAYS = int(os.environ.get("PLAN_DURATION_DAYS", "30"))

PLAN_PRICES_USDT = {
    "pro": float(os.environ.get("PLAN_PRICE_PRO_USDT", "19")),
    "vip": float(os.environ.get("PLAN_PRICE_VIP_USDT", "49")),
}
PLAN_PRICES_STARS = {
    "pro": int(os.environ.get("PLAN_PRICE_PRO_STARS", "1000")),
    "vip": int(os.environ.get("PLAN_PRICE_VIP_STARS", "2500")),
}
PROMO_CODES = {
    "TRADERBURUNDI": {"days": 5},
    "TEDDYPRO": {"days": 7, "role": "pro"},
    "TEDDYVIP": {"days": 7, "role": "vip"},
    "WELCOME": {"days": 5, "role": "tester"},
}

USER_ROLES = ["free", "tester", "pro", "vip", "admin"]
PREMIUM_ROLES = ["pro", "vip", "admin"]

# =========================================================
# 4. LIMITES UTILISATEURS
# =========================================================

FREE_DAILY_REQUESTS = 5
MAX_WATCHLIST_SYMBOLS_FREE = 5
MAX_WATCHLIST_SYMBOLS_TESTER = 25
MAX_WATCHLIST_SYMBOLS_PRO = 100
MAX_ALERTS_FREE = 3
MAX_ALERTS_TESTER = 20
MAX_ALERTS_PRO = 100

# =========================================================
# 5. CACHE & ANALYSE TECHNIQUE
# =========================================================

PRICE_CACHE_TTL = 900
HISTORY_CACHE_TTL = 300

DEFAULT_TIMEFRAME = "1h"
HISTORY_PERIOD = "6mo"
ATR_PERIOD = 14
ATR_MULTIPLIER_SL = 1.60                 # Stop-Loss calibré (1.60x ATR) pour éviter les mèches intra-bougie tout en maîtrisant le risque
RR_RATIO_TARGET = 2.10                   # Objectif Risk/Reward calibré à 2.10R par validation walk-forward hors échantillon

# Paramètres de stratégie par symbole.
#  1. Les valeurs historiques BTC/ETH/XAU sont conservées À L'IDENTIQUE (aucune modification de seuil).
#  2. Les autres symboles héritent des valeurs globales déjà communes à BTC/ETH/XAU (ADX, fenêtres RSI, min_cond).
#  3. Seul le plafond de volatilité (atr_max_pct) est un réglage par symbole. Valeur initiale de COMPATIBILITÉ avec la
#     stratégie existante (même ordre de grandeur que ETH), PAS une valeur optimisée ni validée par backtest.
DEFAULT_SYMBOL_PARAMS = {"adx_min": 22, "rsi_buy_low": 48, "rsi_buy_high": 66, "rsi_sell_low": 34, "rsi_sell_high": 52, "min_cond": 4}
DEFAULT_ATR_MAX_PCT = 4.8  # plafond d'ATR% pour tout symbole sans override explicite

SYMBOL_PARAM_OVERRIDES = {
    "BTCUSDT": {"atr_max_pct": 4.5},
    "ETHUSDT": {"atr_max_pct": 4.8},
    "XAUUSDT": {"atr_max_pct": 2.5},
    # Nouveaux symboles : valeurs initiales explicites et faciles à modifier (voir note ci-dessus).
    "SOLUSDT": {"atr_max_pct": 4.8},
    "XRPUSDT": {"atr_max_pct": 4.8},
    "DOGEUSDT": {"atr_max_pct": 4.8},
    "ADAUSDT": {"atr_max_pct": 4.8},
    "LINKUSDT": {"atr_max_pct": 4.8},
    "SUIUSDT": {"atr_max_pct": 4.8},
    "BNBUSDT": {"atr_max_pct": 4.8},
    "ZECUSDT": {"atr_max_pct": 4.8},
}


def _build_symbol_configs() -> dict:
    out = {}
    for sym in DOCUMENTED_SYMBOLS:
        cfg = dict(DEFAULT_SYMBOL_PARAMS)
        cfg["atr_max_pct"] = DEFAULT_ATR_MAX_PCT
        cfg.update(SYMBOL_PARAM_OVERRIDES.get(sym, {}))
        out[sym] = cfg
    return out


SYMBOL_CONFIGS = _build_symbol_configs()

DATA_DIR = "data"
TWELVEDATA_WS_URL = "wss://ws.twelvedata.com/v1/quotes/price"

# =========================================================
# 6. PAPER TRADING
# =========================================================

PAPER_DEFAULT_CAPITAL  = 10_000.0
PAPER_FEES_PCT         = 0.10
PAPER_SLIPPAGE_PCT     = 0.05
PAPER_DEFAULT_LEVERAGE = 1.0
PAPER_MAX_LEVERAGE     = 10.0
