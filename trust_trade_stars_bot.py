# trust_trade_stars_bot.py
# Telegram Stars bot for Trust Trade Network
# python-telegram-bot==20.7
#
# ENV required:
#   BOT_TOKEN            -> BotFather token
#   OWNER_USERNAME       -> admin username without @ (used in messages)
#   ADMIN_IDS            -> comma-separated chat IDs to notify (supports -100... channel IDs)
#
# Features:
# - Membership tiers: Free(0⭐), Verified(550⭐), Pro(1,500⭐), VIP(5,000⭐), Oil King(300,000⭐)
# - Per-doc: members 150⭐ (verify), guests 350⭐ (verify-guest)
# - In-memory membership (30 days) for gating the 150⭐ member rate
# - Admin alerts on every payment + on Free activation
# - Enhanced UX: improved messages, consistent flow, better button layouts

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

# ===================== ENV & Logging =====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "TrustTradeNetwork_Admin").strip()

_admin_env = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS: List[int] = []
if _admin_env:
    for piece in _admin_env.split(","):
        s = piece.strip()
        if not s:
            continue
        try:
            ADMIN_IDS.append(int(s))
        except ValueError:
            logging.warning(f"Skipping invalid ADMIN_IDS entry: {s}")

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logging.info(f"ADMIN_IDS parsed: {ADMIN_IDS}")

# ===================== Membership Store (MVP) =====================
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
    """150⭐ member doc allowed for paid tiers, NOT for mem-free."""
    t = tier_of(user_id)
    return bool(t and t != "mem-free")

# ===================== Helper Functions =====================
def get_daily_limit(tier_key: str) -> str:
    limits = {
        "mem-verified": "2",
        "mem-pro": "7", 
        "mem-vip": "10",
        "mem-king": "unlimited"
    }
    return limits.get(tier_key, "0")

def get_group_name(tier_key: str) -> str:
    groups = {
        "mem-free": "Free Members group",
        "mem-verified": "Verified Group Users",
        "mem-pro": "Pro group",
        "mem-vip": "VIP group",
        "mem-king": "exclusive Oil King tier"
    }
    return groups.get(tier_key, "appropriate group")

# ===================== Catalog =====================
@dataclass(frozen=True)
class Product:
    key: str
    title: str
    desc: str
    stars: int

MEMBERSHIP_TIERS: List[Product] = [
    Product("mem-free",     "Free Member",     "Free membership — no verifications; Free Members group.", 0),
    Product("mem-verified", "Verified Member", "Monthly Access Tier. Starts on today.", 550),
    Product("mem-pro",      "Pro Member",      "Monthly Access Tier. Starts on today.", 1500),
    Product("mem-vip",      "Vip Member",      "Monthly Access Tier. Starts on today.", 5000),
    Product("mem-king",     "The Oil King",    "Unlimited verifications + dedicated manager.", 300000),
]

PER_DOC_MEMBER = Product("verify",       "Document Verification", "Per-document review (members). 1–4h result.", 150)
PER_DOC_GUEST  = Product("verify-guest", "One-Time Verification", "Per-document (no membership). 1–4h result.", 350)

def find_product(key: str) -> Optional[Product]:
    if key == PER_DOC_MEMBER.key: return PER_DOC_MEMBER
    if key == PER_DOC_GUEST.key:  return PER_DOC_GUEST
    for p in MEMBERSHIP_TIERS:
        if p.key == key: return p
    return None

# ===================== Copy =====================
INTRO = (
    "💠 *Trust Trade Network*\n"
    "*Filter First. Trade Smarter.*\n"
    "━━━━━━━━━━━━━━━━━\n\n"
    "🔍 *What We Verify:*\n"
    "LOIs • ICPOs • SCOs • POP • POF • Crypto Wallets • Mandates\n"
    "_Across oil, gas, metals, and agri commodities worldwide_\n\n"
    "━━━━━━━━━━━━━━━━━\n"
    "💳 *Monthly Memberships* - Pay with ⭐ Telegram Stars\n\n"
    "🆓 *Free Member* — 0⭐ — Community group access, market updates & insights, no document verifications\n\n"
    "✅ *Verified Member* — 550⭐ per month — Up to 2 verifications per day, verified group access, priority support\n\n"
    "⭐ *Pro Member* — 1,500⭐ per month — Up to 7 verifications per day, pro group access, enhanced priority support\n\n"
    "💎 *VIP Member* — 5,000⭐ per month — Up to 10 verifications per day, VIP group access, premium support\n\n"
    "👑 *The Oil King* — 300,000⭐ per month — Unlimited verifications, dedicated personal manager, white-glove service\n\n"
    "━━━━━━━━━━━━━━━━━\n\n"
    "⚡ *Per-Document Options* — Members: 150⭐ each, Non-members: 350⭐ each\n"
    "⏱️ *Turnaround: 1-4 hours* — Complex cases may take longer\n"
    "Choose your membership tier below to get started with Trust Trade Network verification services."
)

WHAT_WE_VERIFY = (
    "🔎 *What we verify*\n"
    "• *Letters & offers:* LOI, ICPO, SCO, SPA excerpts\n"
    "• *Performance proofs:* POP/POF variants, bank letters (format sanity), transaction trails\n"
    "• *Identity & mandate chains:* mandates, intermediaries, signatory roles\n"
    "• *Crypto:* wallet provenance checks (basic heuristics), transfer proofs, custody claims\n"
    "• *Commodities:* oil/petchem, metals, agri — cross-check issuer, dates, tonnage, routing logic\n\n"
    "*Outputs:* PASS / FLAG / REJECT with brief rationale. Not a legal opinion."
)

KING_DETAILS = (
    "👑 *The Oil King — 300,000⭐*\n"
    "Unlimited verifications, priority handling, and a dedicated manager who will:\n\n"
    "• *Filter deals & mitigate risk* — screen offers, spot falsified docs, reduce noise\n"
    "• *Provide multilingual coverage* — English/Russian/Korean with suppliers/refineries across RU/KZ/KR\n"
    "• *Expand vetted supplier access* — ties into major producers/logistics, esp. KZ metals/coal\n"
    "• *Optimize settlement* — assist compliant crypto rails where appropriate to reduce cross-border friction\n"
    "• *Explore digital asset options* — assess tokenized tools for capital/loyalty when strategically aligned\n\n"
    "Use this tier only if you expect active deal flow and want white-glove screening."
)

# ===================== Admin Alerts (UNCHANGED) =====================
async def admin_alert(context: ContextTypes.DEFAULT_TYPE, user, kind: str, package_title: str, amount: int, payload: str):
    if not ADMIN_IDS: return
    uname = f"@{user.username}" if user and getattr(user, "username", None) else f"user_id:{getattr(user, 'id', 'unknown')}"
    text = (
        "💸 Stars payment received\n\n"
        f"From: {uname}\n"
        f"Type: {kind}\n"
        f"Package: {package_title}\n"
        f"Amount: {amount} ⭐\n"
        f"Payload: {payload}\n"
    )
    for a in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=a, text=text)
        except Exception as e:
            logging.warning(f"Admin notify failed for {a}: {e}")

async def admin_info(context: ContextTypes.DEFAULT_TYPE, text: str):
    for a in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=a, text=text)
        except Exception as e:
            logging.warning(f"Admin info failed for {a}: {e}")

# ===================== Keyboards =====================
def home_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Start/home menu with simplified layout."""
    rows: List[List[InlineKeyboardButton]] = []

    # Membership buttons with better formatting
    rows.append([InlineKeyboardButton("🆓 Free Member", callback_data="buy:mem-free")])
    rows.append([InlineKeyboardButton("✅ Verified — 550⭐", callback_data="buy:mem-verified")])
    rows.append([InlineKeyboardButton("⭐ Pro — 1,500⭐", callback_data="buy:mem-pro")])
    rows.append([InlineKeyboardButton("💎 VIP — 5,000⭐", callback_data="buy:mem-vip")])
    rows.append([InlineKeyboardButton("👑 Oil King — 300,000⭐", callback_data="buy:mem-king")])

    # Info buttons
    rows.append([
        InlineKeyboardButton("📋 What We Verify", callback_data="info"),
        InlineKeyboardButton("👑 About Oil King", callback_data="king"),
    ])

    return InlineKeyboardMarkup(rows)

def again_keyboard(product: Optional[Product]=None) -> InlineKeyboardMarkup:
    if not product:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Start Again", callback_data="restart")]])

    if product.key == PER_DOC_MEMBER.key:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Pay Another Document (⭐150)", callback_data=f"buy:{PER_DOC_MEMBER.key}"),
             InlineKeyboardButton("🎫 Buy/ Renew Membership", callback_data="restart")],
            [InlineKeyboardButton("What We Verify ?", callback_data="info"),
             InlineKeyboardButton("🔁 Start Again", callback_data="restart")]
        ])

    if product.key == PER_DOC_GUEST.key:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Pay Another Document (⭐350)", callback_data=f"buy:{PER_DOC_GUEST.key}"),
             InlineKeyboardButton("🎫 Buy/ Renew Membership", callback_data="restart")],
            [InlineKeyboardButton("What We Verify ?", callback_data="info"),
             InlineKeyboardButton("🔁 Start Again", callback_data="restart")]
        ])

    if product.key.startswith("mem-"):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Document Verification — 150⭐", callback_data=f"buy:{PER_DOC_MEMBER.key}"),
             InlineKeyboardButton("What We Verify?", callback_data="info")],
            [InlineKeyboardButton("🔁 Start Again", callback_data="restart")]
        ])

    return InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Start Again", callback_data="restart")]])

# ===================== Invoicing =====================
def _membership_invoice_desc(product_key: str) -> str:
    if product_key == "mem-verified":
        return f"Monthly Access Tier. Starts on {datetime.utcnow().strftime('%b %d, %Y')}"
    elif product_key == "mem-pro":
        return f"Monthly Access Tier. Starts on {datetime.utcnow().strftime('%b %d, %Y')}"
    elif product_key == "mem-vip": 
        return f"Monthly Access Tier. Starts on {datetime.utcnow().strftime('%b %d, %Y')}"
    else:
        return f"Monthly Access Tier. Starts on {datetime.utcnow().strftime('%b %d, %Y')}"

def _doc_invoice_desc(product_key: str) -> str:
    if product_key == PER_DOC_MEMBER.key:
        return "Pre-Document Review (Member)\nResult in 1-4 hours"
    else:
        return "One-Time (no membership) one document verification"

async def send_invoice(chat_id: int, product: Product, context: ContextTypes.DEFAULT_TYPE, user_id: Optional[int]=None) -> None:
    # Free (0⭐) — no invoice, just activate and notify admins
    if product.key == "mem-free":
        MEMBERS[user_id] = {"tier": "mem-free", "paid_at": datetime.utcnow()}
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "✅ *Free membership activated.*\n\n"
                "You now have access to the Free Members group and updates.\n"
                f"Trust Trade Network Administrator will send you the invitation to Free Group.\n\n"
                f"For verification of documents, use *One-Time ({PER_DOC_GUEST.stars}⭐)* or upgrade to a paid membership to receive discounts.\n\n"
                f"If you haven't been contacted by Administrator, DM @TrustTradeNetwork_Admin "
                f"with \"Free Member + telegram id @****\""
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("One-Time (no membership) — 350⭐", callback_data=f"buy:{PER_DOC_GUEST.key}")],
                [InlineKeyboardButton("⬅️ Go Back", callback_data="back"),
                 InlineKeyboardButton("🔁 Start Again", callback_data="restart")]
            ])
        )
        class Dummy: pass
        d = Dummy(); d.username = None; d.id = user_id
        await admin_alert(context, d, "Membership", "Free Member", 0, "FREE")
        return

    # Determine description based on product type
    if product.key.startswith("mem-"):
        desc = _membership_invoice_desc(product.key)
    else:
        desc = _doc_invoice_desc(product.key)
    
    prices = [LabeledPrice(label=product.title, amount=product.stars)]
    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=product.title,
            description=desc,
            payload=f"{product.key}:{product.stars}",
            provider_token="",               # Stars
            currency="XTR",                  # Stars currency
            prices=prices,
            is_flexible=False,
            start_parameter=product.key
        )
    except BadRequest as e:
        logging.warning(f"Invoice error for {product.key}: {e}")
        if product.key == "mem-king":
            await context.bot.send_message(
                chat_id=chat_id,
                text=("👑 This tier requires manual arrangement. Please DM "
                      f"@TrustTradeNetwork_Admin and we'll finalize your onboarding."),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Go Back", callback_data="back"),
                     InlineKeyboardButton("🔁 Start Again", callback_data="restart")]
                ])
            )
            await admin_info(context, f"⚠️ Invoice failed for Oil King (chat {chat_id}).")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Payment temporarily unavailable. Please try again.")
    except TelegramError as e:
        logging.error(f"TelegramError sending invoice: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Payment temporarily unavailable. Please try again later.")

# ===================== Handlers =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    arg = context.args[0] if context.args else None
    if arg:
        prod = find_product(arg.lower())
        if prod:
            if prod.key == PER_DOC_MEMBER.key and not can_use_member_doc(uid):
                await update.effective_chat.send_message(
                    f"{PER_DOC_MEMBER.title} ({PER_DOC_MEMBER.stars}⭐) is available for paid members. "
                    f"Use One-Time ({PER_DOC_GUEST.stars}⭐) or upgrade to a membership.",
                    reply_markup=home_keyboard(uid)
                ); return
            await send_invoice(update.effective_chat.id, prod, context, user_id=uid); return
    await update.effective_chat.send_message(INTRO, parse_mode="Markdown",
                                             reply_markup=home_keyboard(uid))

async def on_menu_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    await q.message.reply_text(INTRO, parse_mode="Markdown", reply_markup=home_keyboard(uid))

async def on_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    await q.message.reply_text("⬅️ Back.", reply_markup=home_keyboard(uid))

async def on_restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    await q.message.reply_text(INTRO, parse_mode="Markdown", reply_markup=home_keyboard(uid))

async def on_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Go Back", callback_data="back"),
         InlineKeyboardButton("🔁 Start Again", callback_data="restart")]
    ])
    await q.message.reply_text(WHAT_WE_VERIFY, parse_mode="Markdown", reply_markup=kb)

async def on_king(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Go Back", callback_data="back"),
         InlineKeyboardButton("🔁 Start Again", callback_data="restart")]
    ])
    await q.message.reply_text(KING_DETAILS, parse_mode="Markdown", reply_markup=kb)

# DEV helpers
async def on_dev_mem(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    MEMBERS[uid] = {"tier": "mem-verified", "paid_at": datetime.utcnow()}
    await q.message.reply_text(
        "✅ *DEV:* Simulated membership payment (Verified Member).",
        parse_mode="Markdown",
        reply_markup=home_keyboard(uid)
    )
    await admin_alert(context, q.from_user, "Membership", "Verified Member", 550, "DEV")

async def on_dev_verify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if not can_use_member_doc(uid):
        await q.message.reply_text(
            f"{PER_DOC_MEMBER.title} ({PER_DOC_MEMBER.stars}⭐) is for paid members. "
            f"Use One-Time ({PER_DOC_GUEST.stars}⭐) or upgrade.",
            reply_markup=home_keyboard(uid)
        ); return
    await q.message.reply_text(
        "✅ *Payment received for document verification.*\n\n"
        f"Amount: *{PER_DOC_MEMBER.stars}⭐*\n"
        f"Next: DM @TrustTradeNetwork_Admin with \"READY + your name\". We'll collect your documents.",
        parse_mode="Markdown",
        reply_markup=again_keyboard(PER_DOC_MEMBER)
    )
    await admin_alert(context, q.from_user, "Per-Document", PER_DOC_MEMBER.title, PER_DOC_MEMBER.stars, "DEV")

async def on_buy_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    key = (q.data or "").split(":", 1)[1] if ":" in (q.data or "") else ""
    
    if not key:
        await q.message.reply_text("Error: Invalid selection. Please try again.", reply_markup=home_keyboard(q.from_user.id))
        return
    
    prod = find_product(key)
    if not prod:
        await q.message.reply_text("Unknown package. Use /start.", reply_markup=home_keyboard(q.from_user.id))
        return
    
    uid = q.from_user.id
    if prod.key == PER_DOC_MEMBER.key and not can_use_member_doc(uid):
        await q.message.reply_text(
            f"{PER_DOC_MEMBER.title} ({PER_DOC_MEMBER.stars}⭐) is available for paid members. "
            f"Use One-Time ({PER_DOC_GUEST.stars}⭐) or upgrade.",
            reply_markup=home_keyboard(uid)
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
            f"🎉 *Congratulations — you are {prod.title.lower()}!*\n\n"
            f"You can now verify {get_daily_limit(prod.key)} documents a day for *150⭐* each.\n"
            f"You also will be invited to {get_group_name(prod.key)}.\n\n"
            f"If you haven't received invitation for 1 hour, please DM "
            f"@TrustTradeNetwork_Admin"
        )
        await update.message.reply_text(msg, parse_mode="Markdown",
                                        reply_markup=home_keyboard(user.id))
        await admin_alert(context, user, "Membership", prod.title, sp.total_amount, payload)
    else:
        kind = "Per-Document (Member)" if prod.key == PER_DOC_MEMBER.key else "Per-Document (One-Time)"
        await update.message.reply_text(
            "✅ *Payment received for document verification.*\n\n"
            f"Amount: *{sp.total_amount}⭐*\n"
            f"Next: DM @TrustTradeNetwork_Admin We'll collect your documents.",
            parse_mode="Markdown",
            reply_markup=again_keyboard(prod)
        )
        await admin_alert(context, user, kind, prod.title, sp.total_amount, payload)

# ===================== Main =====================
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))

    app.add_handler(CallbackQueryHandler(on_menu_home, pattern=r"^menu$"))
    app.add_handler(CallbackQueryHandler(on_back, pattern=r"^back$"))
    app.add_handler(CallbackQueryHandler(on_restart, pattern=r"^restart$"))

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
