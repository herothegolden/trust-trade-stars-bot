
# file: stars_invoice_bot.py
# Minimal invoice-only Telegram bot using Telegram Stars (XTR).
# - Presents package options
# - Sends a Stars invoice (no provider_token needed)
# - Confirms on payment success, then instructs the user to DM you manually
#
# Setup:
#   1) Create a bot with @BotFather and copy the token.
#   2) pip install python-telegram-bot==20.7
#   3) Set BOT_TOKEN and OWNER_USERNAME below (or use env vars).
#   4) python stars_invoice_bot.py
#
# Notes:
# - For Stars payments (digital goods), currency="XTR" and provider_token="" (empty) is okay.
# - This bot does NOT store to a DB; it's just to validate payments.
# - You can extend to subscriptions later by using subscription_period.
#
# Docs:
# - Payments for digital goods via Stars (sendInvoice with XTR, provider_token optional): https://core.telegram.org/bots/payments-stars
# - Bot API reference (XTR currency): https://core.telegram.org/bots/api

from __future__ import annotations
import logging
import os
from dataclasses import dataclass

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, PreCheckoutQueryHandler
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "YourUsername")  # where users should DM you after paying

@dataclass(frozen=True)
class Package:
    key: str
    name: str
    stars: int
    desc: str

# Edit these
PACKAGES = [
    Package("basic", "Basic Verification", 100, "Single document check. 24–48h."),
    Package("full", "Full Verification", 250, "Multi-doc review + risk flags. 24–48h."),
    Package("vip",  "VIP Priority",      500, "Priority queue + analyst call."),
]

def packages_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{p.name} — {p.stars} ⭐️", callback_data=f"buy:{p.key}")] for p in PACKAGES]
    return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_chat.send_message(
        "Trust Trade — Stars Checkout\n\nChoose a package to pay with ⭐️ Telegram Stars.",
        reply_markup=packages_keyboard()
    )

def get_pkg(key: str) -> Package | None:
    for p in PACKAGES:
        if p.key == key:
            return p
    return None

async def on_buy_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if not data.startswith("buy:"):
        return
    key = data.split(":", 1)[1]
    pkg = get_pkg(key)
    if not pkg:
        await q.message.reply_text("Unknown package. Try again with /start.")
        return

    # For Stars: amounts are in Stars units (XTR has no fractional digits).
    prices = [LabeledPrice(label=pkg.name, amount=pkg.stars)]

    await context.bot.send_invoice(
        chat_id=q.message.chat_id,
        title=pkg.name,
        description=pkg.desc,
        payload=f"pkg:{pkg.key}:{pkg.stars}",
        provider_token="",          # empty for Stars / digital goods
        currency="XTR",             # Telegram Stars
        prices=prices,
        start_parameter="single",   # or use a deep link param you like
        is_flexible=False
    )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Always answer pre-checkout within 10s
    await update.pre_checkout_query.answer(ok=True)

async def on_success(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    # Basic confirmation
    await update.message.reply_text(
        "✅ Payment received. Thanks!\n\n"
        f"Next: DM @{OWNER_USERNAME} with “READY + your name”. "
        "We’ll collect your documents and start verification."
    )

def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Set BOT_TOKEN in the file or as an env var.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_buy_click, pattern=r"^buy:"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(CommandHandler("help", start))
    # Successful payment handler must be a MessageHandler, but PTB 20.7 allows using add_handler on message updates via filters in more complex setup.
    # Simpler: rely on default handler for successful_payment on messages:
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_success))

    app.run_polling()

if __name__ == "__main__":
    main()
