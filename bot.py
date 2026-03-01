import os
import logging
from datetime import datetime, timedelta
from pymongo import MongoClient
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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

# Helper functions
def get_user(user_id):
    return users_collection.find_one({"user_id": user_id})

def create_user(user_id, username=None):
    user = {
        "user_id": user_id,
        "username": username,
        "balance": 1000,
        "alive": True,
        "death_time": None
    }
    users_collection.insert_one(user)
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

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    existing = get_user(user_id)
    if existing:
        # Update username in case it changed
        if existing.get("username") != username:
            update_user(user_id, {"username": username})
        await update.message.reply_text("You are already registered. Use /balance to check your balance.")
    else:
        create_user(user_id, username)
        await update.message.reply_text("Welcome! You have been credited with 1000 Rs. Use /balance to check.")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("You are not registered. Please use /start first.")
        return
    user, revived = check_and_revive(user)
    status = "Alive" if user["alive"] else "Dead"
    msg = f"Your balance: {user['balance']} Rs\nStatus: {status}"
    if revived:
        msg += "\n(You have been automatically revived after 5 hours.)"
    await update.message.reply_text(msg)

async def kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Must reply to a user
    if not update.message.reply_to_message:
        await update.message.reply_text("You need to reply to a user's message to kill them.")
        return

    killer_id = update.effective_user.id
    target_id = update.message.reply_to_message.from_user.id
    if killer_id == target_id:
        await update.message.reply_text("You cannot kill yourself.")
        return

    # Get users
    killer = get_user(killer_id)
    if not killer:
        await update.message.reply_text("You are not registered. Please use /start first.")
        return
    target = get_user(target_id)
    if not target:
        await update.message.reply_text("Target is not registered. They need to /start first.")
        return

    # Auto‑revive if time expired
    killer, _ = check_and_revive(killer)
    target, _ = check_and_revive(target)

    # Checks
    if not killer["alive"]:
        await update.message.reply_text("You are dead and cannot kill. Use /revive to revive yourself or wait 5 hours.")
        return
    if not target["alive"]:
        await update.message.reply_text("Target is already dead. You cannot kill a dead person.")
        return

    # Perform kill
    now = datetime.utcnow()
    new_killer_balance = killer["balance"] + 500
    update_user(killer_id, {"balance": new_killer_balance})
    update_user(target_id, {"alive": False, "death_time": now})

    await update.message.reply_text(
        f"You killed {target['username'] or target_id} and gained 500 Rs!\n"
        f"Your new balance: {new_killer_balance} Rs"
    )

async def revive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reviver = get_user(user_id)
    if not reviver:
        await update.message.reply_text("You are not registered. Please use /start first.")
        return

    # Determine target
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        reviving_self = (target_id == user_id)
    else:
        target_id = user_id
        reviving_self = True

    target = get_user(target_id)
    if not target:
        await update.message.reply_text("Target is not registered.")
        return

    # Auto‑revive target if time expired
    target, _ = check_and_revive(target)

    if reviving_self:
        # Self revive
        if target["alive"]:
            await update.message.reply_text("You are already alive.")
            return
        cost = 100
        if target["balance"] < cost:
            await update.message.reply_text(f"You don't have enough balance to revive. You need {cost} Rs.")
            return
        new_balance = target["balance"] - cost
        update_user(target_id, {"alive": True, "death_time": None, "balance": new_balance})
        await update.message.reply_text(f"You have revived yourself! Cost: {cost} Rs. New balance: {new_balance} Rs")
    else:
        # Revive another user
        reviver, _ = check_and_revive(reviver)
        if not reviver["alive"]:
            await update.message.reply_text("You are dead and cannot revive others. Revive yourself first.")
            return
        if target["alive"]:
            await update.message.reply_text("Target is already alive.")
            return
        cost = 100
        if reviver["balance"] < cost:
            await update.message.reply_text(f"You don't have enough balance to revive. You need {cost} Rs.")
            return
        new_reviver_balance = reviver["balance"] - cost
        update_user(user_id, {"balance": new_reviver_balance})
        update_user(target_id, {"alive": True, "death_time": None})
        await update.message.reply_text(
            f"You revived {target['username'] or target_id}! Cost: {cost} Rs. Your new balance: {new_reviver_balance} Rs"
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("kill", kill))
    application.add_handler(CommandHandler("revive", revive))
    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
