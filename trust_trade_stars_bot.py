# file: trust_trade_stars_bot.py
# Trust Trade Stars Bot
# Features:
# - ONE bot handles both monthly membership tiers and per-document payments.
# - Monthly tiers (non-recurring): Free Member 250⭐️, Verified 550⭐️, Pro 1500⭐️, Vip 5000⭐️, The King 10000⭐️
# - Per-document verification: 150⭐️ each time.
# - Deep links: ?start=mem-free|mem-verified|mem-pro|mem-vip|mem-king|verify
# - Admin alerts on successful payments with user id & package.
#
# Notes:
# - Stars subscriptions (true recurring) exist, but this v1 uses one-time monthly charges (manual renewal) for simplicity/PTB 20.7.
# - You (admin) manually track entitlements/limits per tier for now.
#
# Run:
#   pip install python-telegram-bot==20.7
#   BOT_TOKEN=xxx OWNER_USERNAME=YourUsername ADMIN_IDS=123456789,987654321 python trust_trade_stars_bot.py
#
# Railway:
#   - Service Type: Worker
#   - Start Command: python -u trust_trade_stars_bot.py
#   - Variables: BOT_TOKEN, OWNER_USERNAME, ADMIN_IDS

from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from typing import Optional, List

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "YourUsername")
_admin_env = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS: List[int] = [int(x.strip()) for x in _admin_env.split(",") if x.strip().isdigit()] if _admin_env else []

# ---------- Catalog ----------
@dataclass(frozen=True)
class Product:
    key: str
    title: str
    desc: str
    stars: int

MEMBERSHIP_TIERS: List[Product] = [
    Product("mem-free",     "Free Member",     "Monthly access tier (manual renewal).", 250),
    Product("mem-verified", "Verified Member", "Monthly access tier (manual renewal).", 550),
    Product("mem-pro",      "Pro Member",      "Monthly access tier (manual renewal).", 1500),
    Product("mem-vip",      "Vip Member",      "Monthly access tier (manual renewal).", 5000),
    Product("mem-king",     "The King",        "Monthly access tier (manual renewal).", 10000),
]

PER_DOC = Product("verify", "Document Verification", "Per-document review. 24–48h result.", 150)

def find_product(key: str) -> Optional[Product]:
    if key == PER_DOC.key:
        return PER_DOC
    for p in MEMBERSHIP_TIERS:
        if p.key == key:
            return p
    return None

# ---------- Keyboards ----------
def membership_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{p.title} — {p.stars} ⭐️", callback_data=f"buy:{p.key}")] for p in MEMBERSHIP_TIERS]
    rows.append([InlineKeyboardButton(f"{PER_DOC.title} — {PER_DOC.stars} ⭐️", callback_data=f"buy:{PER_DOC.key}")])
    return InlineKeyboardMarkup(rows)

def main_menu_text() -> str:
    return (
        "Trust Trade — Stars Checkout\n\n"
        "Choose a package to pay with ⭐️ Telegram Stars.\n\n"
        "Monthly tiers (manual renewal):\n"
        "• Free Member — 250⭐️\n"
        "• Verified Member — 550⭐️\n"
        "• Pro Member — 1500⭐️\n"
        "• Vip Member — 5000⭐️\n"
        "• The King — 10,000⭐️\n\n"
        f"Per-document verification: {PER_DOC.stars}⭐️ each.\n"
        "After payment, DM @" + OWNER_USERNAME + " with “READY + your name”.\n"
        "Turnaround: 24–48h."
    )

def again_keyboard(product: Optional[Product]=None) -> InlineKeyboardMarkup:
    if product and product.key != PER_DOC.key:
        # membership: offer "Pay per document" and "Renew membership"
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"➕ Pay per document ({PER_DOC.stars}⭐️)", callback_data=f"buy:{PER_DOC.key}")],
            [InlineKeyboardButton(f"🔁 Renew {product.title}", callback_data=f"buy:{product.key}")],
        ])
    elif product and product.key == PER_DOC.key:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"➕ Pay another document ({PER_DOC.stars}⭐️)", callback_data=f"buy:{PER_DOC.key}")],
            [InlineKeyboardButton("🏷️ Buy/renew membership", callback_data="menu")],
        ])
    else:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🏷️ Choose a package", callback_data="menu")]])

# ---------- Invoicing ----------
async def send_invoice(chat_id: int, product: Product, context: ContextTypes.DEFAULT_TYPE) -> None:
    prices = [LabeledPrice(label=product.title, amount=product.stars)]
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=product.title,
        description=product.desc,
        payload=f"{product.key}:{product.stars}",
        provider_token="",   # empty for Telegram Stars
        currency="XTR",      # Stars
        prices=prices,
        is_flexible=False,
        start_parameter=product.key
    )

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Deep links: /start mem-free|mem-verified|mem-pro|mem-vip|mem-king|verify
    arg = context.args[0] if context.args else None
    if arg:
        prod = find_product(arg.lower())
        if prod:
            await send_invoice(update.effective_chat.id, prod, context)
            return
    await update.effective_chat.send_message(main_menu_text(), reply_markup=membership_keyboard())

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(main_menu_text(), reply_markup=membership_keyboard())

async def on_buy_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if not data.startswith("buy:"):
        return
    key = data.split(":", 1)[1]
    prod = find_product(key)
    if not prod:
        await q.message.reply_text("Unknown package. Use /start.")
        return
    await send_invoice(q.message.chat_id, prod, context)

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.pre_checkout_query.answer(ok=True)

async def on_success(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    payload = sp.invoice_payload or ""
    pkey = payload.split(":")[0] if ":" in payload else payload
    prod = find_product(pkey) or Product(pkey, pkey.title(), "", sp.total_amount)
    user = update.effective_user

    # Notify buyer
    if prod.key.startswith("mem-"):
        msg = (
            "✅ Membership payment received. Thank you!\n\n"
            f"Tier: *{prod.title}*\n"
            f"Next: DM @{OWNER_USERNAME} with “READY + your name”. "
            "We’ll confirm your membership and collect your documents.\n\n"
            "_Note: This is a monthly charge without auto-renewal. Pay again next month to renew._"
        )
    else:
        msg = (
            "✅ Payment received for document verification.\n\n"
            f"Amount: *{sp.total_amount}⭐️*\n"
            f"Next: DM @{OWNER_USERNAME} with “READY + your name”. "
            "We’ll collect your documents and start review."
        )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=again_keyboard(prod))

    # Admin alert
    if ADMIN_IDS:
        uname = f"@{user.username}" if user and user.username else f"user_id:{user.id if user else 'unknown'}"
        text = (
            "💸 Stars payment received\n\n"
            f"From: {uname}\n"
            f"Type: {'Membership' if prod.key.startswith('mem-') else 'Per-Document'}\n"
            f"Package: {prod.title}\n"
            f"Amount: {sp.total_amount} ⭐️\n"
            f"Payload: {payload}\n"
        )
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=text)
            except Exception as e:
                logging.warning(f"Failed to notify admin {admin_id}: {e}")

def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set.")
    if OWNER_USERNAME == "YourUsername":
        logging.warning("OWNER_USERNAME is still 'YourUsername'. Set OWNER_USERNAME env var.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(on_menu, pattern=r"^menu$"))
    app.add_handler(CallbackQueryHandler(on_buy_click, pattern=r"^buy:"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_success))

    app.run_polling()

if __name__ == "__main__":
    main()
