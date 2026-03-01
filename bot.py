import os
import logging
import random
import threading
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, filters

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["telegram_game_bot"]
users_collection = db["users"]

# Cooldown storage (in-memory)
last_rob = {}      # user_id -> datetime
last_kill = {}     # user_id -> datetime

# ---------- Minimal HTTP Server for Render Web Service ----------
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        # Suppress HTTP server logs
        return

def run_http_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"HTTP server listening on port {port}")
    server.serve_forever()
# -----------------------------------------------------------------

# Helper functions
def get_user(user_id):
    return users_collection.find_one({"user_id": user_id})

def create_user(user_id, username=None, referrer_id=None):
    user = {
        "user_id": user_id,
        "username": username,
        "balance": 1000,
        "alive": True,
        "death_time": None
    }
    users_collection.insert_one(user)
    
    # If referred, give referrer 5000 Rs (if referrer exists and is different)
    if referrer_id and referrer_id != user_id:
        referrer = get_user(referrer_id)
        if referrer:
            new_balance = referrer["balance"] + 5000
            update_user(referrer_id, {"balance": new_balance})
            logger.info(f"Referrer {referrer_id} gained 5000 Rs for referring {user_id}")
    return user

def update_user(user_id, update):
    users_collection.update_one({"user_id": user_id}, {"$set": update})

def check_and_revive(user):
    """Auto‑revive user if death_time + 5 hours passed."""
    if not user["alive"] and user["death_time"] is not None:
        death_time = user["death_time"]
        if isinstance(death_time, datetime):
            if datetime.utcnow() >= death_time + timedelta(hours=5):
                update_user(user["user_id"], {"alive": True, "death_time": None})
                user["alive"] = True
                user["death_time"] = None
                return user, True
    return user, False

def get_or_create_user(user_id, username=None, referrer_id=None):
    user = get_user(user_id)
    if not user:
        user = create_user(user_id, username, referrer_id)
    elif username and user.get("username") != username:
        update_user(user_id, {"username": username})
        user["username"] = username
    return user

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    
    # Check for referral in start argument
    referrer_id = None
    if context.args and len(context.args) > 0:
        # Expected format: ref_123456
        match = re.match(r"ref_(\d+)", context.args[0])
        if match:
            referrer_id = int(match.group(1))
    
    # Get or create user (with possible referrer)
    db_user = get_or_create_user(user_id, username, referrer_id)
    
    welcome = (
        f"🎮 <b>Welcome to the Game Bot!</b>\n\n"
        f"💰 You have been credited with <b>1000 Rs</b>.\n"
        f"💡 Use /help to see all commands.\n"
        f"🎯 Invite friends with /invite and earn <b>5000 Rs</b> each!"
    )
    if referrer_id and referrer_id != user_id:
        welcome += f"\n\n✨ You joined through a friend's invite!"
    
    await update.message.reply_text(welcome, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📜 <b>Game Commands</b>\n\n"
        "🎮 /start – Register and get 1000 Rs\n"
        "💰 /bal – Check your balance and status\n"
        "🔪 /kill – Reply to someone to kill them (gain 500 Rs, target dies 5h)\n"
        "💊 /revive – Revive yourself or reply to revive someone (cost 100 Rs)\n"
        "🦹 /rob – Reply to rob someone (steal 50-300 Rs, 1min cooldown)\n"
        "📨 /invite – Get your personal invite link (works only in DM)\n"
        "ℹ️ /help – Show this message"
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    db_user = get_or_create_user(user_id, username)
    db_user, revived = check_and_revive(db_user)
    
    status_emoji = "🟢 Alive" if db_user["alive"] else "🔴 Dead"
    msg = (
        f"👤 <b>Your Profile</b>\n\n"
        f"💰 Balance: <b>{db_user['balance']} Rs</b>\n"
        f"⚰️ Status: {status_emoji}"
    )
    if revived:
        msg += f"\n\n✨ You have been automatically revived after 5 hours!"
    await update.message.reply_text(msg, parse_mode='HTML')

async def kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Cooldown check
    if user_id in last_kill:
        time_diff = datetime.utcnow() - last_kill[user_id]
        if time_diff < timedelta(minutes=5):
            remaining = timedelta(minutes=5) - time_diff
            minutes, seconds = divmod(remaining.seconds, 60)
            await update.message.reply_text(
                f"⏳ <b>Cooldown!</b> You must wait {minutes}m {seconds}s before using /kill again.",
                parse_mode='HTML'
            )
            return
    
    # Must reply to a user
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ <b>You need to reply to a user's message to kill them.</b>",
            parse_mode='HTML'
        )
        return

    killer_id = user_id
    target_id = update.message.reply_to_message.from_user.id
    target_username = update.message.reply_to_message.from_user.username

    if killer_id == target_id:
        await update.message.reply_text("😵 <b>You cannot kill yourself.</b>", parse_mode='HTML')
        return

    # Get or create users
    killer = get_or_create_user(killer_id, username)
    target = get_or_create_user(target_id, target_username)

    # Auto‑revive
    killer, _ = check_and_revive(killer)
    target, _ = check_and_revive(target)

    # Check killer alive
    if not killer["alive"]:
        await update.message.reply_text(
            "💀 <b>You are dead!</b> Revive yourself first with /revive.",
            parse_mode='HTML'
        )
        return

    # Case: target already dead → penalize killer
    if not target["alive"]:
        penalty = 500
        if killer["balance"] < penalty:
            await update.message.reply_text(
                f"⚠️ <b>You tried to kill a dead person, but you don't have {penalty} Rs to pay the penalty!</b>",
                parse_mode='HTML'
            )
            return
        new_balance = killer["balance"] - penalty
        update_user(killer_id, {"balance": new_balance})
        # Update cooldown even if failed? Better not, to avoid punishing twice. We'll skip cooldown for failed kill.
        await update.message.reply_text(
            f"❌ <b>You attempted to kill someone already dead!</b>\n"
            f"As punishment you lose <b>{penalty} Rs</b>.\n"
            f"💸 New balance: <b>{new_balance} Rs</b>",
            parse_mode='HTML'
        )
        return

    # Normal kill
    now = datetime.utcnow()
    new_killer_balance = killer["balance"] + 500
    update_user(killer_id, {"balance": new_killer_balance})
    update_user(target_id, {"alive": False, "death_time": now})
    
    # Set cooldown
    last_kill[user_id] = now
    
    await update.message.reply_text(
        f"🔪 <b>You killed {target_username or target_id}!</b>\n"
        f"💰 You gained <b>500 Rs</b>.\n"
        f"💵 New balance: <b>{new_killer_balance} Rs</b>",
        parse_mode='HTML'
    )

async def revive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    reviver = get_or_create_user(user_id, username)

    # Determine target
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_username = update.message.reply_to_message.from_user.username
        reviving_self = (target_id == user_id)
    else:
        target_id = user_id
        target_username = username
        reviving_self = True

    target = get_or_create_user(target_id, target_username)
    target, _ = check_and_revive(target)

    if reviving_self:
        # Self revive
        if target["alive"]:
            await update.message.reply_text("✅ <b>You are already alive.</b>", parse_mode='HTML')
            return
        cost = 100
        if target["balance"] < cost:
            await update.message.reply_text(
                f"💔 <b>You don't have enough balance to revive.</b> Need <b>{cost} Rs</b>.",
                parse_mode='HTML'
            )
            return
        new_balance = target["balance"] - cost
        update_user(target_id, {"alive": True, "death_time": None, "balance": new_balance})
        await update.message.reply_text(
            f"💊 <b>You revived yourself!</b>\n"
            f"💰 Cost: <b>{cost} Rs</b>\n"
            f"💵 New balance: <b>{new_balance} Rs</b>",
            parse_mode='HTML'
        )
    else:
        # Revive another
        reviver, _ = check_and_revive(reviver)
        if not reviver["alive"]:
            await update.message.reply_text(
                "💀 <b>You are dead!</b> Revive yourself first.",
                parse_mode='HTML'
            )
            return
        if target["alive"]:
            await update.message.reply_text("✅ <b>Target is already alive.</b>", parse_mode='HTML')
            return
        cost = 100
        if reviver["balance"] < cost:
            await update.message.reply_text(
                f"💔 <b>You don't have enough balance to revive.</b> Need <b>{cost} Rs</b>.",
                parse_mode='HTML'
            )
            return
        new_reviver_balance = reviver["balance"] - cost
        update_user(user_id, {"balance": new_reviver_balance})
        update_user(target_id, {"alive": True, "death_time": None})
        await update.message.reply_text(
            f"💊 <b>You revived {target_username or target_id}!</b>\n"
            f"💰 Cost: <b>{cost} Rs</b>\n"
            f"💵 Your new balance: <b>{new_reviver_balance} Rs</b>",
            parse_mode='HTML'
        )

async def rob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Cooldown check
    if user_id in last_rob:
        time_diff = datetime.utcnow() - last_rob[user_id]
        if time_diff < timedelta(minutes=1):
            remaining = timedelta(minutes=1) - time_diff
            seconds = remaining.seconds
            await update.message.reply_text(
                f"⏳ <b>Cooldown!</b> You must wait {seconds}s before robbing again.",
                parse_mode='HTML'
            )
            return

    # Must reply to a user
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ <b>You need to reply to a user's message to rob them.</b>",
            parse_mode='HTML'
        )
        return

    robber_id = user_id
    target_id = update.message.reply_to_message.from_user.id
    target_username = update.message.reply_to_message.from_user.username

    if robber_id == target_id:
        await update.message.reply_text("🤔 <b>You cannot rob yourself.</b>", parse_mode='HTML')
        return

    robber = get_or_create_user(robber_id, username)
    target = get_or_create_user(target_id, target_username)

    robber, _ = check_and_revive(robber)
    target, _ = check_and_revive(target)

    if not robber["alive"]:
        await update.message.reply_text("💀 <b>You are dead!</b> Revive first.", parse_mode='HTML')
        return
    if not target["alive"]:
        await update.message.reply_text("⚰️ <b>Target is dead.</b> You can't rob a corpse.", parse_mode='HTML')
        return

    steal_amount = random.randint(50, 300)
    actual_steal = min(steal_amount, target["balance"])

    if actual_steal == 0:
        await update.message.reply_text(
            f"😅 <b>You tried to rob {target_username or target_id}, but they have no money!</b>",
            parse_mode='HTML'
        )
        return

    new_target_balance = target["balance"] - actual_steal
    new_robber_balance = robber["balance"] + actual_steal
    update_user(target_id, {"balance": new_target_balance})
    update_user(robber_id, {"balance": new_robber_balance})
    
    # Set cooldown
    last_rob[user_id] = datetime.utcnow()

    funny_lines = [
        f"🦹 <b>You snatched {actual_steal} Rs from {target_username or target_id} and vanished like a ninja!</b>",
        f"💰 <b>Quick hands! You lifted {actual_steal} Rs from {target_username or target_id} while they were checking their phone.</b>",
        f"😈 <b>Pickpocketing success! +{actual_steal} Rs from {target_username or target_id}. They'll never know it was you...</b>",
        f"🎭 <b>Disguised as a bush, you grabbed {actual_steal} Rs from {target_username or target_id}. Master of stealth!</b>",
        f"💨 <b>You ran past {target_username or target_id} and stole {actual_steal} Rs. They're still looking around confused.</b>",
    ]
    await update.message.reply_text(random.choice(funny_lines), parse_mode='HTML')

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only work in private chat
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            "📨 <b>Invite command works only in bot's DM.</b>\n"
            "Please start a private chat with me and use /invite there.",
            parse_mode='HTML'
        )
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    get_or_create_user(user_id, username)  # ensure user exists
    
    bot_username = context.bot.username
    invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    text = (
        f"🎁 <b>Your Personal Invite Link</b>\n\n"
        f"🔗 <code>{invite_link}</code>\n\n"
        f"👥 For each friend who joins using this link, you get <b>5000 Rs</b>!\n"
        f"💡 Share this link with your friends and watch your balance grow."
    )
    await update.message.reply_text(text, parse_mode='HTML')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main():
    # Start HTTP server thread (for Render Web Service)
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("bal", bal))
    application.add_handler(CommandHandler("kill", kill))
    application.add_handler(CommandHandler("revive", revive))
    application.add_handler(CommandHandler("rob", rob))
    application.add_handler(CommandHandler("invite", invite))
    
    application.add_error_handler(error_handler)
    
    application.run_polling()

if __name__ == "__main__":
    main()
