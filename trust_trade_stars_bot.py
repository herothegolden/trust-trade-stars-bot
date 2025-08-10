# Trust Trade Stars Bot — memberships + per-doc + info buttons
# python-telegram-bot==20.7
# Env: BOT_TOKEN, OWNER_USERNAME (no @), ADMIN_IDS="123,456"

from __future__ import annotations
import logging, os
from dataclasses import dataclass
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
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
    Product("mem-king",     "The Oil King",    "Unlimited verifications + dedicated manager.", 300000),
]

PER_DOC = Product("verify", "Document Verification", "Per-document review. 24–48h result.", 150)

def find_product(key: str) -> Optional[Product]:
    if key == PER_DOC.key: return PER_DOC
    for p in MEMBERSHIP_TIERS:
        if p.key == key: return p
    return None

# ---------- Copy ----------
INTRO = (
    "💠 *Trust Trade Network*\n"
    "*Filter First. Trade Smarter.*\n\n"
    "We verify *LOIs, ICPOs, SCOs, POP, POF, crypto wallets, and mandates* across oil, gas, metals, agri, and more.\n\n"
    "Choose a package to pay with ⭐️ Telegram Stars.\n\n"
    "*Monthly tiers (manual renewal):*\n"
    "• *Free Member* — 250⭐️ — no verifications; Free Members group\n"
    "• *Verified Member* — 550⭐️ — up to 2 verifications/day; Verified group\n"
    "• *Pro Member* — 1500⭐️ — up to 7 verifications/day; Pro group\n"
    "• *Vip Member* — 5000⭐️ — up to 10 verifications/day; VIP group\n"
    "• *The Oil King* — 300,000⭐️ — unlimited verifications + dedicated manager (details below)\n\n"
    f"*Per-document verification:* {PER_DOC.stars}⭐️ each.\n"
    f"After payment, DM *@{OWNER_USERNAME}* with “READY + your name”.\n"
    "_Turnaround: 24–48h. Usage limits are managed manually at this stage._"
)

WHAT_WE_VERIFY = (
    "🔎 *What we verify*\n"
    "• Letters & offers: LOI, ICPO, SCO, SPA excerpts\n"
    "• Performance proofs: POP/POF variants, bank letters (format sanity), transaction trails\n"
    "• Identity & mandate chains: mandates, intermediaries, signatory roles\n"
    "• Crypto: wallet provenance checks (basic heuristics), transfer proofs, custody claims\n"
    "• Commodities: oil/petchem, metals, agri — cross-check issuer, dates, tonnage, routing logic\n\n"
    "Outputs: PASS / FLAG / REJECT with brief rationale. Not a legal opinion."
)

KING_DETAILS = (
    "👑 *The Oil King — 300,000⭐️*\n"
    "Unlimited verifications, priority handling, and a dedicated manager who will:\n\n"
    "• *Filter deals & mitigate risk* — screen offers, spot falsified docs, reduce noise\n"
    "• *Provide multilingual coverage* — English/Russian/Korean with suppliers/refineries across RU/KZ/KR\n"
    "• *Expand vetted supplier access* — ties into major producers/logistics, esp. KZ metals/coal\n"
    "• *Optimize settlement* — assist compliant crypto rails where appropriate to reduce cross-border friction\n"
    "• *Explore digital asset options* — assess tokenized tools for capital/loyalty when strategically aligned\n\n"
    "Use this tier only if you expect active deal flow and want white-glove screening."
)

# ---------- Keyboards ----------
def membership_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{p.title} — {p.stars} ⭐️", callback_data=f"buy:{p.key}")] for p in MEMBERSHIP_TIERS]
    rows.append([InlineKeyboardButton(f"{PER_DOC.title} — {PER_DOC.stars} ⭐️", callback_data=f"buy:{PER_DOC.key}")])
    rows.append([
        InlineKeyboardButton("ℹ️ What we verify", callback_data="info"),
        InlineKeyboardButton("👑 Oil King details", callback_data="king"),
    ])
    return InlineKeyboardMarkup(rows)

def again_keyboard(product: Optional[Product]=None) -> InlineKeyboardMarkup:
    if product and product.key != PER_DOC.key:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"➕ Pay per document ({PER_DOC.stars}⭐️)", callback_data=f"buy:{PER_DOC.key}")],
            [InlineKeyboardButton(f"🔁 Renew {product.title}", callback_data=f"buy:{product.key}")],
            [InlineKeyboardButton("ℹ️ What we verify", callback_data="info")],
        ])
    elif product and product.key == PER_DOC.key:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"➕ Pay another document ({PER_DOC.stars}⭐️)", callback_data=f"buy:{PER_DOC.key}")],
            [InlineKeyboardButton("🏷️ Buy/renew membership", callback_data="menu")],
            [InlineKeyboardButton("ℹ️ What we verify", callback_data="info")],
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
        provider_token="",   # Stars (digital goods)
        currency="XTR",
        prices=prices,
        is_flexible=False,
        start_parameter=product.key
    )

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = context.args[0] if context.args else None
    if arg:
        prod = find_product(arg.lower())
        if prod:
            await send_invoice(update.effective_chat.id, prod, context)
            return
    await update.effective_chat.send_message(INTRO, parse_mode="Markdown", reply_markup=membership_keyboard())

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await q.message.reply_text(INTRO, parse_mode="Markdown", reply_markup=membership_keyboard())

async def on_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await q.message.reply_text(WHAT_WE_VERIFY, parse_mode="Markdown")

async def on_king(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await q.message.reply_text(KING_DETAILS, parse_mode="Markdown")

async def on_buy_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    key = (q.data or "").split(":", 1)[1]
    prod = find_product(key)
    if not prod:
        await q.message.reply_text("Unknown package. Use /start.")
        return
    await send_invoice(q.message.chat_id, prod, context)

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.pre_checkout_query.answer(ok=True)

async def on_success(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sp = update.message.successful_payment
    pkey = (sp.invoice_payload or "").split(":")[0]
    prod = find_product(pkey) or Product(pkey, pkey.title(), "", sp.total_amount)
    user = update.effective_user
    if prod.key.startswith("mem-"):
        msg = (
            "✅ *Membership payment received.*\n\n"
            f"Tier: *{prod.title}*\n"
            f"Next: DM *@{OWNER_USERNAME}* with “READY + your name”. "
            "We’ll confirm your membership and collect your documents.\n\n"
            "_Monthly charge; renew manually next month._"
        )
    else:
        msg = (
            "✅ *Payment received for document verification.*\n\n"
            f"Amount: *{sp.total_amount}⭐️*\n"
            f"Next: DM *@{OWNER_USERNAME}* with “READY + your name”. "
            "We’ll collect your documents and start review."
        )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=again_keyboard(prod))

    if ADMIN_IDS:
        uname = f"@{user.username}" if user and user.username else f"user_id:{user.id if user else 'unknown'}"
        text = (
            "💸 Stars payment received\n\n"
            f"From: {uname}\n"
            f"Type: {'Membership' if prod.key.startswith('mem-') else 'Per-Document'}\n"
            f"Package: {prod.title}\n"
            f"Amount: {sp.total_amount} ⭐️\n"
            f"Payload: {sp.invoice_payload}\n"
        )
        for a in ADMIN_IDS:
            try: await context.bot.send_message(chat_id=a, text=text)
            except Exception as e: logging.warning(f"Admin notify failed {a}: {e}")

def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is not set.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(on_menu, pattern=r"^menu$"))
    app.add_handler(CallbackQueryHandler(on_info, pattern=r"^info$"))
    app.add_handler(CallbackQueryHandler(on_king, pattern=r"^king$"))
    app.add_handler(CallbackQueryHandler(on_buy_click, pattern=r"^buy:"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_success))
    app.run_polling()

if __name__ == "__main__":
    main()
