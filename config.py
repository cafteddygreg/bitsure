import os

# =========================================================
# 1. LES SEULES VARIABLES À ENREGISTRER SUR RENDER / .ENV
# =========================================================
# Tu n'as besoin de configurer que ces 3 variables (et éventuellement TWELVEDATA_API_KEY) :
# - TELEGRAM_TOKEN
# - ADMIN_ID
# - DATABASE_URL

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN manquant dans l'environnement")

_raw_admin_id = os.environ.get("ADMIN_ID", "@btsrteddy").strip()
try:
    ADMIN_ID = int(_raw_admin_id)
except ValueError:
    ADMIN_ID = 0

ADMIN_USERNAME = _raw_admin_id if not _raw_admin_id.lstrip("-").isdigit() else "@btsrteddy"
if not ADMIN_USERNAME.startswith("@"):
    ADMIN_USERNAME = f"@{ADMIN_USERNAME}"

DATABASE_URL = os.environ.get("DATABASE_URL")

# Optionnel (uniquement si tu analyses XAUUSD / Forex hors Binance ou reçois des paiements Binance Pay)
TWELVEDATA_API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
BINANCE_ID = os.environ.get("BINANCE_ID", "")

# Optionnel : Clé API Gemini pour l'interpréteur de logs (/logs)
# Utilise par défaut gemini-3.1-flash-lite (ultra-rapide et très économe en tokens).
# Si vide, l'interpréteur de logs fonctionne quand même à 100% grâce à son moteur de diagnostic local (0 token).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_LOG_MODEL = os.environ.get("GEMINI_LOG_MODEL", "gemini-3.1-flash-lite")

# =========================================================
# 2. CONFIGURATION PAR DÉFAUT AUTOTRADE & SÉCURITÉ
# (Tout est géré ici directement en Python, aucune variable Render requise)
# =========================================================

# Mode Testnet par défaut (False = Argent réel sur Binance, True = Testnet)
BINANCE_TESTNET = True

# Clés Binance Futures Testnet par défaut (https://testnet.binancefuture.com)
DEFAULT_BINANCE_TESTNET_API_KEY = os.environ.get(
    "BINANCE_TESTNET_API_KEY",
    "QNdiAbB7f2k4GRhnRdztYBP67ZhRheBV8TneqgAA0aXUGGJ7krr4CiJlIvnDGufr",
)
DEFAULT_BINANCE_TESTNET_API_SECRET = os.environ.get(
    "BINANCE_TESTNET_API_SECRET",
    "OGzSc3BkNUZoSs754hfXWUeJRSIfK5vsKJxECbdzgO540jyKkdaVAmNKVnFAa5u7",
)

# Clés Binance Spot Testnet par défaut (https://testnet.binance.vision)
DEFAULT_BINANCE_SPOT_TESTNET_API_KEY = os.environ.get(
    "BINANCE_SPOT_TESTNET_API_KEY",
    "wTKgkH0mkEre1MKPjDfZ5Re09YNhPV6BLdRReGbTRIM9gnu3aDHloAPat6VvJEFl",
)
DEFAULT_BINANCE_SPOT_TESTNET_API_SECRET = os.environ.get(
    "BINANCE_SPOT_TESTNET_API_SECRET",
    "SgEARZTSzEMOZ1VHorVQrY9JX0RHisGi4GUDApkJl1LEgd6JOvqLLkC4JOK7iFVd",
)

# Paramètres par défaut d'un profil de trading
AUTO_TRADE_DEFAULT = False
PERIODIC_ANALYSIS_DEFAULT = False
DEFAULT_MARKET_TYPE = "futures"          # "futures" ou "spot"
DEFAULT_TRADING_STYLE = "day"            # "scalping", "scalping_15m", "day", "swing", "position"
DEFAULT_ANALYSIS_TIMEFRAME = "1h"        # "5m", "15m", "1h", "4h", "1d"
DEFAULT_ANALYSIS_INTERVAL_MINUTES = 5    # 5 ou 10 minutes
DEFAULT_LEVERAGE = 1                     # Levier x1 par défaut
DEFAULT_RISK_PER_TRADE = 1.0             # 1.0% du capital risqué par trade
DEFAULT_MAX_POSITIONS = 3                # Max 3 positions simultanées
DEFAULT_MIN_SCORE = 70                   # Score Teddy minimum (sur 100)
DEFAULT_MAX_DAILY_LOSS = 5.0             # Perte journalière max (5%)
DEFAULT_TRAILING_STOP = False
DEFAULT_DCA_ENABLED = False

# Plafonds de risque et délais de sécurité
MAX_POSITION_EXPOSURE_PCT = 50.0         # Exposition max par position (50% du capital)
SIGNAL_VALIDITY_SECONDS = 900            # Validité d'un signal (15 minutes)
DEFAULT_SAFETY_LOCK_TTL_SECONDS = 3600   # Auto-downgrade du safe_mode critique après 1h (3600s)

# Pool PostgreSQL
DB_POOL_MINCONN = 1
DB_POOL_MAXCONN = 10

# =========================================================
# 3. ACCÈS & UTILISATEURS
# =========================================================

ACCESS_MODE = "approved_only"
ALLOW_AUTO_REGISTER = True
TRIAL_DAYS = 30

USER_ROLES = ["tester", "pro", "admin"]
PREMIUM_ROLES = ["pro", "admin"]

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
ATR_MULTIPLIER_SL = 1.5
RR_RATIO_TARGET = 2.0

SYMBOL_CONFIGS = {
    "BTCUSD": {"adx_min": 23, "rsi_buy_low": 48, "rsi_buy_high": 68, "rsi_sell_low": 32, "rsi_sell_high": 52, "atr_max_pct": 5.5, "min_cond": 4},
    "ETHUSD": {"adx_min": 22, "rsi_buy_low": 47, "rsi_buy_high": 70, "rsi_sell_low": 30, "rsi_sell_high": 56, "atr_max_pct": 6.0, "min_cond": 4},
    "BTCUSDT": {"adx_min": 25, "rsi_buy_low": 50, "rsi_buy_high": 65, "rsi_sell_low": 35, "rsi_sell_high": 50, "atr_max_pct": 4.5, "min_cond": 4},
    "ETHUSDT": {"adx_min": 24, "rsi_buy_low": 50, "rsi_buy_high": 67, "rsi_sell_low": 33, "rsi_sell_high": 50, "atr_max_pct": 5.0, "min_cond": 4},
    "XAUUSD": {"adx_min": 24, "rsi_buy_low": 48, "rsi_buy_high": 74, "rsi_sell_low": 26, "rsi_sell_high": 52, "atr_max_pct": 3.0, "min_cond": 4},
}

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
