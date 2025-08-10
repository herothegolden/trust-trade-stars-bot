# Trust Trade Stars Bot — memberships + per-doc + info buttons + membership gating + Dev Button
# python-telegram-bot==20.7
# Env: BOT_TOKEN, OWNER_USERNAME (no @), ADMIN_IDS="123,456"

from __future__ import annotations
import logging, os
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters
)
from telegram.error import BadRequest, TelegramError

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "YourUsername")
_admin_env = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS: List[int] = [int(x.strip()) for x in _admin_env.split(",") if x.strip().isdigit()] if _admin_env else []

# --------- Membership tracking (in-memory MVP) ---------
MEMBERSHIP_DURATION_DAYS = 30
MEMBERS: Dict[int, Dict[str, object]] = {}  # user_id -> {"tier": "mem-pro", "paid_at": datetime}

def is_member(user_id: int) -> bool:
    rec = MEMBERS.get(user_id)
    if not rec:
        return False
    return datetime.utcnow() - rec["paid_at"] <= timedelta(days=MEMBERSHIP_DURATION_DAYS)

# ---------- Catalog ----------
@dataclass(frozen=True)
class Product:
    key: str
    title: str
    desc: str
    stars: int

MEMBERSHIP_TIERS: List[Product] = [
    Product("mem-free",     "Free Member",     "Monthly Access Tier. Starts on today.", 250),
    Product("mem-verified", "Verified Member", "Monthly Access Tier. Starts on today.", 550),
    Product("mem-pro",      "Pro Member",      "Monthly Access Tier. Starts on today.", 1500),
    Product("mem-vip",      "Vip Member",      "Monthly Access Tier. Starts on today.", 5000),
    Product("mem-king",     "The Oil King",    "Monthly Access Tier. Starts on today.", 300000),
]

# ⬇️ Updated per-doc copy (1–4h)
PER_DOC = Product("verify", "Document Verification", "Per-document review. 1–4h result depending on the document.", 150)

def find_product(key: str) -> Optional[Product]:
    if key == PER_DOC.key: return PER_DOC
    for p in MEMBERSHIP_TIERS:
        if p.key == key: return p
    return None

# ---------- Copy ----------
INTRO = (
    "💠 *Trust Trade Network*\n"
    "*Filter First. Trade Smarter.*\n\n"
    "We verify *LOIs, ICPOs, SCOs, POP, POF, crypto wallets, and mandates* across oil, gas, metals, and agri.\n\n"
    "Choose a package to pay with ⭐️ Telegram Stars.\n\n"
    "*Monthly tiers (manual renewal):*\n"
    "• *Free Member* — 250⭐️ · no verifications · Free group\n"
    "• *Verified Member* — 550⭐️ · up to 2 verifications/day · Verified group\n"
    "• *Pro Member* — 1500⭐️ · up to 7 verifications/day · Pro group\n"
    "• *Vip Member* — 5000⭐️ · up to 10 verifications/day · VIP group\n"
    "• *The Oil King* — 300,000⭐️ · unlimited verifications + dedicated manager (details below)\n\n"
    f"*Per-document verification:* {PER_DOC.stars}⭐️ each (visible after membership purchase).\n"
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
    "• *Explore digital asset options* — assess tokenized tools for capital/loyalty when aligned\n\n"
    "Use this tier only if you expect active deal flow and want white-glove screening."
)

# ---------- Keyboards ----------
def membership_keyboard_for(user_id: int) -> InlineKeyboardMarkup:
    # If member: show ONLY the per-doc button (as requested)
    if is_member(user_id):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{PER_DOC.title} — {PER_DOC.stars} ⭐️", callback_data=f"buy:{PER_DOC.key}")]
        ])
    # If not a member: show tiers + info + Dev button
    rows = [[InlineKeyboardButton(f"{p.title} — {p.stars} ⭐️", callback_data=f"buy:{p.key}")]
            for p in MEMBERSHIP_TIERS]
    rows.append([
        InlineKeyboardButton("ℹ️ What we verify", callback_data="info"),
        InlineKeyboardButton("👑 Oil King details", callback_data="king"),
    ])
    rows.append([InlineKeyboardButton("Dev Button", callback_data="dev")])  # simulate membership
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
def _membership_invoice_desc() -> str:
    return f"Monthly Access Tier. Starts on {datetime.utcnow().strftime('%b %d, %Y')}"

async def send_invoice(chat_id: int, product: Product, context: ContextTypes.DEFAULT_TYPE) -> None:
    desc = _membership_invoice_desc() if product.key.startswith("mem-") else product.desc
    prices = [LabeledPrice(label=product.title, amount=product.stars)]
    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=product.title,
            description=desc,
            payload=f"{product.key}:{product.stars}",
            provider_token="",  # Stars (digital goods)
            currency="XTR",
            prices=prices,
            is_flexible=False,
            start_parameter=product.key
        )
    except BadRequest as e:
        logging.warning(f"Invoice error for {product.key}: {e}")
        if product.key == "mem-king":
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "👑 This tier requires manual arrangement. Please DM "
                    f"@{OWNER_USERNAME} and we’ll finalize your onboarding."
                )
            )
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"⚠️ Invoice failed for The Oil King (user chat {chat_id}). Contact them manually."
                    )
                except Exception as ex:
                    logging.warning(f"Admin notify failed {admin_id}: {ex}")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Payment temporarily unavailable. Please try again.")
    except TelegramError as e:
        logging.error(f"TelegramError sending invoice: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Payment temporarily unavailable. Please try again later.")

# ---------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = context.args[0] if context.args else None
    uid = update.effective_user.id
    if arg:
        prod = find_product(arg.lower())
        if prod:
            if prod.key == PER_DOC.key and not is_member(uid):
                await update.effective_chat.send_message(
                    "Per-document payments are available after you purchase a membership.",
                    reply_markup=membership_keyboard_for(uid)
                )
                return
            await send_invoice(update.effective_chat.id, prod, context)
            return
    await update.effective_chat.send_message(
        INTRO, parse_mode="Markdown", reply_markup=membership_keyboard_for(uid)
    )

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    await q.message.reply_text(INTRO, parse_mode="Markdown",
                               reply_markup=membership_keyboard_for(uid))

async def on_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await q.message.reply_text(WHAT_WE_VERIFY, parse_mode="Markdown")

async def on_king(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await q.message.reply_text(KING_DETAILS, parse_mode="Markdown")

async def on_dev(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    MEMBERS[uid] = {"tier": "mem-verified", "paid_at": datetime.utcnow()}
    await q.message.reply_text(
        "✅ *DEV:* Simulated membership payment (Verified Member).\n\n"
        f"Next: DM *@{OWNER_USERNAME}* with “READY + your name”.",
        parse_mode="Markdown",
        reply_markup=membership_keyboard_for(uid)  # now shows ONLY per-doc button
    )
    for a in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=a, text=f"🧪 DEV: Simulated membership for user_id:{uid}")
        except Exception as e:
            logging.warning(f"Admin notify failed {a}: {e}")

async def on_buy_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    key = (q.data or "").split(":", 1)[1]
    prod = find_product(key)
    if not prod:
        await q.message.reply_text("Unknown package. Use /start."); return
    if prod.key == PER_DOC.key and not is_member(q.from_user.id):
        await q.message.reply_text(
            "Per-document payments are available after you purchase a membership.",
            reply_markup=membership_keyboard_for(q.from_user.id)
        )
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

    if prod.key.startswith("mem-"):
        MEMBERS[user.id] = {"tier": prod.key, "paid_at": datetime.utcnow()}
        msg = (
            "✅ *Membership payment received.*\n\n"
            f"Tier: *{prod.title}*\n"
            f"Next: DM *@{OWNER_USERNAME}* with “READY + your name”. "
            "We’ll confirm your membership and collect your documents.\n\n"
            "_Monthly charge; renew manually next month._"
        )
        await update.message.reply_text(msg, parse_mode="Markdown",
                                        reply_markup=membership_keyboard_for(user.id))  # ONLY per-doc button now
    else:
        msg = (
            "✅ *Payment received for document verification.*\n\n"
            f"Amount: *{sp.total_amount}⭐️*\n"
            f"Next: DM *@{OWNER_USERNAME}* with “READY + your name”. "
            "We’ll collect your documents and start review."
        )
        await update.message.reply_text(msg, parse_mode="Markdown",
                                        reply_markup=again_keyboard(prod))

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
    app.add_handler(CallbackQueryHandler(on_dev, pattern=r"^dev$"))
    app.add_handler(CallbackQueryHandler(on_buy_click, pattern=r"^buy:"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_success))
    app.run_polling()

if __name__ == "__main__":
    main()
