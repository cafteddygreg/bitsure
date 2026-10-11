import hashlib
import time
from config import BINANCE_ID, PLAN_PRICES_USDT
from i18n import get_text

def generate_binance_payment(user_id: int, lang: str, plan: str = "pro") -> tuple:
    plan_key = "vip" if str(plan or "pro").strip().lower() == "vip" else "pro"
    raw_amount = PLAN_PRICES_USDT.get(plan_key, 19)
    amount_str = str(int(raw_amount)) if float(raw_amount).is_integer() else f"{float(raw_amount):.2f}"
    ident = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8].upper()
    if plan_key == "vip":
        ident = f"VIP-{ident}"
    text = get_text(lang, "binance_payment_info", amount=amount_str, binance_id=BINANCE_ID, memo=ident)
    return ident, text
