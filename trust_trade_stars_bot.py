# Trust Trade Stars Bot — updated pricing, Free(0⭐️), One-Time 350⭐️, member-only 150⭐️
# python-telegram-bot==20.7
# Env:
#   BOT_TOKEN
#   OWNER_USERNAME              (no @)
#   ADMIN_IDS                   (comma-separated chat IDs; supports -100... channels)

from __future__ import annotations
import logging, os
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters
)
from telegram.error import BadRequest, TelegramError

# -------- ENV / logging ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "YourUsername").strip()
_admin_env = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS: List[int] = []
if _admin_env:
    for chunk in _admin_env.split(","):
        s = chunk.strip()
        if not s:
            continue
        try:
            ADMIN_IDS.append(int(s))
        except ValueError:
            logging.warning(f"Skipping invalid ADMIN_IDS entry: {s}")
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.info(f"ADMIN_IDS parsed: {ADMIN_IDS}")

# -------- Membership storage (in-memory MVP) ----------
MEMBERSHIP_DURATION_DAYS = 30
# user_id -> {"tier": "mem-verified|mem-pro|mem-vip|mem-king|mem-free", "paid_at": datetime}
MEMBERS: Dict[int, Dict[str, object]] = {}

def is_member(user_id: int) -> bool:
    rec = MEMBERS.get(user_id)
    if not rec:
        return False
    return datetime.utcnow() - rec["paid_at"] <= timedelta(days=MEMBERSHIP_DURATION_DAYS)

def tier_of(user_id: int) -> Optional[str]:
    return MEMBERS.get(user_id, {}).get("tier") if is_member(user_id) else None

def can_use_member_doc(user_id: int) -> bool:
    """150⭐️ member doc allowed for all paid tiers, NOT for mem-free."""
    t = tier_of(user_id)
    return bool(t and t != "mem-free")

# -------- Catalog ----------
@dataclass(frozen=True)
class Product:
    key: str
    title: str
    desc: str
    stars: int

# Memberships (Free now 0⭐️)
MEMBERSHIP_TIERS: List[Product] = [
    Product("mem-free",     "Free Member",     "Free membership — no verifications; Free Members group.", 0),
    Product("mem-verified", "Verified Member", "Monthly Access Tier. Starts on today.", 550),
    Product("mem-pro",      "Pro Member",      "Monthly Access Tier. Starts on today.", 1500),
    Product("mem-vip",      "Vip Member",      "Monthly Access Tier. Starts on today.", 5000),
    Product("mem-king",     "The Oil King",    "Unlimited verifications + dedicated manager.", 300000),
]

# Per-document products
PER_DOC_MEMBER = Product("verify",        "Document Verification", "Per-document review (members). 1–4h result.", 150)
PER_DOC_GUEST  = Product("verify-guest",  "One-Time Verification", "Per-document (no membership). 1–4h result.", 350)

def find_product(key: str) -> Optional[Product]:
    if key == PER_DOC_MEMBER.key: return PER_DOC_MEMBER
    if key == PER_DOC_GUEST.key:  return PER_DOC_GUEST
    for p in MEMBERSHIP_TIERS:
        if p.key == key: return p
    return None

# -------- Copy ----------
INTRO = (
    "💠 *Trust Trade Network*\n"
    "*Filter First. Trade Smarter.*\n\n"
    "We verify *LOIs, ICPOs, SCOs, POP, POF, crypto wallets, and mandates* across oil, gas, metals, and agri.\n\n"
    "Choose a package to pay with ⭐️ Telegram Stars.\n\n"
    "*Monthly tiers (manual renewal):*\n"
    "• *Free Member* — 0⭐️ · no verifications · Free group\n"
    "• *Verified Member* — 550⭐️/month · up to 2 verifications/day · Verified group\n"
    "• *Pro Member* — 1,500⭐️/month · up to 7 verifications/day · Pro group\n"
    "• *Vip Member* — 5,000⭐️/month · up to 10 verifications/day · VIP group\n"
    "• *The Oil King* — 300,000⭐️/month · unlimited verifications + dedicated manager (details below)\n\n"
    f"*Per-document options:*\n"
    f"• *Members* — {PER_DOC_MEMBER.stars}⭐️ each (visible for paid tiers)\n"
    f"• *One-Time (no membership)* — {PER_DOC_GUEST.stars}⭐️ each\n\n"
    f"After payment, DM *@{OWNER_USERNAME}* with “READY + your name”.\n"
    "_Turnaround: 1–4h for most documents; complex cases may take longer._"
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
    "Unlimited verifications, priority handling, and a dedicated manager (EN/RU/KR) with vetted supplier access and settlement guidance."
)

# -------- Admin alert ----------
async def admin_alert(context: ContextTypes.DEFAULT_TYPE, user, kind: str, package_title: str, amount: int, payload: str):
    if not ADMIN_IDS: return
    uname = f"@{user.username}" if user and getattr(user, "username", None) else f"user_id:{getattr(user, 'id', 'unknown')}"
    text = (
        "💸 Stars payment received\n\n"
        f"From: {uname}\n"
        f"Type: {kind}\n"
        f"Package: {package_title}\n"
        f"Amount: {amount} ⭐️\n"
        f"Payload: {payload}\n"
    )
    for a in ADMIN_IDS:
        try: await context.bot.send_message(chat_id=a, text=text)
        except Exception as e: logging.warning(f"Admin notify failed for {a}: {e}")

async def admin_info(context: ContextTypes.DEFAULT_TYPE, text: str):
    for a in ADMIN_IDS:
        try: await context.bot.send_message(chat_id=a, text=text)
        except Exception as e: logging.warning(f"Admin info failed for {a}: {e}")

# -------- Keyboards ----------
def keyboard_for_user(user_id: int) -> InlineKeyboardMarkup:
    """Non-members: Free (0), One-Time 350, paid tiers. Members: per-doc member 150 if eligible; else one-time + upgrades."""
    rows: List[List[InlineKeyboardButton]] = []
    t = tier_of(user_id)
    if is_member(user_id):
        if can_use_member_doc(user_id):
            rows.append([InlineKeyboardButton(f"{PER_DOC_MEMBER.title} — {PER_DOC_MEMBER.stars} ⭐️", callback_data=f"buy:{PER_DOC_MEMBER.key}")])
            rows.append([InlineKeyboardButton("Dev Button", callback_data="dev_verify")])
        else:
            # mem-free: show One-Time + upgrades
            rows.append([InlineKeyboardButton(f"{PER_DOC_GUEST.title} — {PER_DOC_GUEST.stars} ⭐️", callback_data=f"buy:{PER_DOC_GUEST.key}")])
            rows.append([InlineKeyboardButton("Upgrade to Verified — 550 ⭐️", callback_data="buy:mem-verified")])
            rows.append([InlineKeyboardButton("Upgrade to Pro — 1500 ⭐️", callback_data="buy:mem-pro")])
            rows.append([InlineKeyboardButton("Upgrade to VIP — 5000 ⭐️", callback_data="buy:mem-vip")])
            rows.append([InlineKeyboardButton("👑 Oil King", callback_data="king")])
            rows.append([InlineKeyboardButton("Dev Button", callback_data="dev_mem")])
        rows.append([
            InlineKeyboardButton("ℹ️ What we verify", callback_data="info"),
        ])
        return InlineKeyboardMarkup(rows)

    # Non-member
    rows.append([InlineKeyboardButton("Free Member — 0 ⭐️", callback_data="buy:mem-free")])
    rows.append([InlineKeyboardButton(f"One-Time Verification — {PER_DOC_GUEST.stars} ⭐️", callback_data=f"buy:{PER_DOC_GUEST.key}")])
    rows.append([InlineKeyboardButton("Verified Member — 550 ⭐️", callback_data="buy:mem-verified")])
    rows.append([InlineKeyboardButton("Pro Member — 1500 ⭐️", callback_data="buy:mem-pro")])
    rows.append([InlineKeyboardButton("Vip Member — 5000 ⭐️", callback_data="buy:mem-vip")])
    rows.append([InlineKeyboardButton("The Oil King — 300000 ⭐️", callback_data="buy:mem-king")])
    rows.append([
        InlineKeyboardButton("ℹ️ What we verify", callback_data="info"),
        InlineKeyboardButton("👑 Oil King details", callback_data="king"),
    ])
    rows.append([InlineKeyboardButton("Dev Button", callback_data="dev_mem")])
    return InlineKeyboardMarkup(rows)

def again_keyboard(product: Optional[Product]=None) -> InlineKeyboardMarkup:
    if product:
        if product.key == PER_DOC_MEMBER.key:
            return InlineKeyboardMarkup([
                [InlineKeyboardButton(f"➕ Pay another document ({PER_DOC_MEMBER.stars}⭐️)", callback_data=f"buy:{PER_DOC_MEMBER.key}")],
                [InlineKeyboardButton("🏷️ Buy/renew membership", callback_data="menu")],
                [InlineKeyboardButton("ℹ️ What we verify", callback_data="info")],
            ])
        if product.key == PER_DOC_GUEST.key:
            return InlineKeyboardMarkup([
                [InlineKeyboardButton(f"➕ Pay another one-time ({PER_DOC_GUEST.stars}⭐️)", callback_data=f"buy:{PER_DOC_GUEST.key}")],
                [InlineKeyboardButton("🏷️ Upgrade to membership", callback_data="menu")],
                [InlineKeyboardButton("ℹ️ What we verify", callback_data="info")],
            ])
        if product.key.startswith("mem-"):
            return InlineKeyboardMarkup([
                [InlineKeyboardButton(f"➕ Pay per document ({PER_DOC_MEMBER.stars}⭐️)", callback_data=f"buy:{PER_DOC_MEMBER.key}")],
                [InlineKeyboardButton("ℹ️ What we verify", callback_data="info")],
            ])
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏷️ Choose a package", callback_data="menu")]])

# -------- Invoicing helpers ----------
def _membership_invoice_desc() -> str:
    return f"Monthly Access Tier. Starts on {datetime.utcnow().strftime('%b %d, %Y')}"

async def send_invoice(chat_id: int, product: Product, context: ContextTypes.DEFAULT_TYPE, user_id: Optional[int]=None) -> None:
    # Special case: Free (0⭐️) — activate without invoice
    if product.key == "mem-free":
        MEMBERS[user_id] = {"tier": "mem-free", "paid_at": datetime.utcnow()}
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ *Free membership activated.*\n\n"
                "You now have access to the Free Members group and updates.\n"
                f"For verification, use *One-Time ({PER_DOC_GUEST.stars}⭐️)* or upgrade to a paid membership.",
            ),
            parse_mode="Markdown",
            reply_markup=keyboard_for_user(user_id)
        )
        # Inform admins
        class Dummy: pass
        d = Dummy(); d.username = None; d.id = user_id
        await admin_alert(context, d, "Membership", "Free Member", 0, "FREE")
        return

    desc = _membership_invoice_desc() if product.key.startswith("mem-") else product.desc
    prices = [LabeledPrice(label=product.title, amount=product.stars)]
    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=product.title,
            description=desc,
            payload=f"{product.key}:{product.stars}",
            provider_token="",
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
                text=( "👑 This tier requires manual arrangement. "
                       f"Please DM @{OWNER_USERNAME} and we’ll finalize your onboarding." )
            )
            await admin_info(context, f"⚠️ Invoice failed for Oil King (chat {chat_id}).")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Payment temporarily unavailable. Please try again.")
    except TelegramError as e:
        logging.error(f"TelegramError sending invoice: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Payment temporarily unavailable. Please try again later.")

# -------- Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    arg = context.args[0] if context.args else None
    uid = update.effective_user.id
    if arg:
        prod = find_product(arg.lower())
        if prod:
            # Gate member 150⭐️ for paid members only
            if prod.key == PER_DOC_MEMBER.key and not can_use_member_doc(uid):
                await update.effective_chat.send_message(
                    f"{PER_DOC_MEMBER.title} ({PER_DOC_MEMBER.stars}⭐️) is available for paid members. "
                    f"Use One-Time ({PER_DOC_GUEST.stars}⭐️) or upgrade to a membership.",
                    reply_markup=keyboard_for_user(uid)
                ); return
            await send_invoice(update.effective_chat.id, prod, context, user_id=uid); return
    await update.effective_chat.send_message(INTRO, parse_mode="Markdown",
                                             reply_markup=keyboard_for_user(uid))

async def on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    await q.message.reply_text(INTRO, parse_mode="Markdown",
                               reply_markup=keyboard_for_user(uid))

async def on_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await q.message.reply_text(WHAT_WE_VERIFY, parse_mode="Markdown")

async def on_king(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    await q.message.reply_text(KING_DETAILS, parse_mode="Markdown")

# DEV buttons
async def on_dev_mem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    MEMBERS[uid] = {"tier": "mem-verified", "paid_at": datetime.utcnow()}
    await q.message.reply_text(
        "✅ *DEV:* Simulated membership payment (Verified Member).",
        parse_mode="Markdown",
        reply_markup=keyboard_for_user(uid)
    )
    await admin_alert(context, q.from_user, "Membership", "Verified Member", 550, "DEV")

async def on_dev_verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if not can_use_member_doc(uid):
        await q.message.reply_text(
            f"{PER_DOC_MEMBER.title} ({PER_DOC_MEMBER.stars}⭐️) is for paid members. "
            f"Use One-Time ({PER_DOC_GUEST.stars}⭐️) or upgrade.",
            reply_markup=keyboard_for_user(uid)
        ); return
    await q.message.reply_text(
        "✅ *Payment received for document verification.*\n\n"
        f"Amount: *{PER_DOC_MEMBER.stars}⭐️*\n"
        f"Next: DM *@{OWNER_USERNAME}* with “READY + your name”. We’ll collect your documents.",
        parse_mode="Markdown",
        reply_markup=again_keyboard(PER_DOC_MEMBER)
    )
    await admin_alert(context, q.from_user, "Per-Document", PER_DOC_MEMBER.title, PER_DOC_MEMBER.stars, "DEV")

async def on_buy_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    key = (q.data or "").split(":", 1)[1]
    prod = find_product(key)
    if not prod:
        await q.message.reply_text("Unknown package. Use /start."); return
    uid = q.from_user.id
    if prod.key == PER_DOC_MEMBER.key and not can_use_member_doc(uid):
        await q.message.reply_text(
            f"{PER_DOC_MEMBER.title} ({PER_DOC_MEMBER.stars}⭐️) is available for paid members. "
            f"Use One-Time ({PER_DOC_GUEST.stars}⭐️) or upgrade.",
            reply_markup=keyboard_for_user(uid)
        ); return
    await send_invoice(q.message.chat_id, prod, context, user_id=uid)

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
            "We’ll confirm your membership and collect your documents."
        )
        await update.message.reply_text(msg, parse_mode="Markdown",
                                        reply_markup=keyboard_for_user(user.id))
        await admin_alert(context, user, "Membership", prod.title, sp.total_amount, payload)
    else:
        kind = "Per-Document (Member)" if prod.key == PER_DOC_MEMBER.key else "Per-Document (One-Time)"
        await update.message.reply_text(
            "✅ *Payment received for document verification.*\n\n"
            f"Amount: *{sp.total_amount}⭐️*\n"
            f"Next: DM *@{OWNER_USERNAME}* with “READY + your name”. We’ll collect your documents.",
            parse_mode="Markdown",
            reply_markup=again_keyboard(prod)
        )
        await admin_alert(context, user, kind, prod.title, sp.total_amount, payload)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(on_menu, pattern=r"^menu$"))
    app.add_handler(CallbackQueryHandler(on_info, pattern=r"^info$"))
    app.add_handler(CallbackQueryHandler(on_king, pattern=r"^king$"))
    app.add_handler(CallbackQueryHandler(on_dev_mem, pattern=r"^dev_mem$"))
    app.add_handler(CallbackQueryHandler(on_dev_verify, pattern=r"^dev_verify$"))
    app.add_handler(CallbackQueryHandler(on_buy_click, pattern=r"^buy:"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_success))
    app.run_polling()

if __name__ == "__main__":
    main()
