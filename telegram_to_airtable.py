import os
import requests
import datetime
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CommandHandler, CallbackContext, ConversationHandler
from flask import Flask, request, jsonify
import threading

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TABLE_NAME = "Telegram messages"
INSTRUCTOR_TABLE_NAME = "Instructor"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Airtable API URLs
AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
INSTRUCTOR_URL = f"https://api.airtable.com/v0/{BASE_ID}/{INSTRUCTOR_TABLE_NAME}"

# Flask app for handling webhook
app = Flask(__name__)

# Telegram bot application (properly initialized)
bot_app = Application.builder().token(TOKEN).build()

# Conversation states
ASK_NAME, ASK_EMAIL = range(2)

# Dictionary to track user registration progress
user_registration = {}

async def set_webhook():
    """Sets the webhook for Telegram Bot."""
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"✅ Webhook set: {WEBHOOK_URL}/webhook")
    else:
        logger.error("❌ ERROR: WEBHOOK_URL is missing!")

def fetch_instructor_by_name(name):
    """Fetch instructor record by name."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.get(INSTRUCTOR_URL, headers=headers)
    
    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            if record["fields"].get("Name", "").strip().lower() == name.strip().lower():
                return record
    return None

def fetch_instructor_by_email(email, name):
    """Fetch instructor record by email (after verifying name)."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.get(INSTRUCTOR_URL, headers=headers)
    
    if response.status_code == 200:
        records = response.json().get("records", [])
        for record in records:
            if record["fields"].get("Name", "").strip().lower() == name.strip().lower():
                if record["fields"].get("Email", "").strip().lower() == email.strip().lower():
                    return record
    return None

def save_telegram_id(record_id, telegram_id):
    """Save Telegram ID to Airtable for instructor."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "fields": {
            "Telegram ID": str(telegram_id)
        }
    }
    url = f"{INSTRUCTOR_URL}/{record_id}"
    response = requests.patch(url, json=data, headers=headers)
    return response.status_code == 200

async def start_registration(update: Update, context: CallbackContext):
    """Start registration process."""
    user_id = update.message.from_user.id
    await update.message.reply_text("Please enter your full name as registered.")
    user_registration[user_id] = {"step": ASK_NAME}
    return ASK_NAME

async def ask_for_email(update: Update, context: CallbackContext):
    """Handle name input and ask for email."""
    user_id = update.message.from_user.id
    name = update.message.text.strip()
    
    record = fetch_instructor_by_name(name)
    if record:
        user_registration[user_id] = {"step": ASK_EMAIL, "name": name, "record_id": record["id"]}
        await update.message.reply_text("Name found. Now enter your registered email.")
        return ASK_EMAIL
    else:
        await update.message.reply_text("❌ Name not found in database. Please contact the office.")
        return ConversationHandler.END

async def complete_registration(update: Update, context: CallbackContext):
    """Handle email input and complete registration."""
    user_id = update.message.from_user.id
    email = update.message.text.strip()
    
    if user_id in user_registration and "name" in user_registration[user_id]:
        name = user_registration[user_id]["name"]
        record_id = user_registration[user_id]["record_id"]

        record = fetch_instructor_by_email(email, name)
        if record:
            success = save_telegram_id(record_id, user_id)
            if success:
                await update.message.reply_text(f"✅ Thank you, {name}! Your Telegram ID has been linked.")
            else:
                await update.message.reply_text("❌ Error saving your Telegram ID. Please try again later.")
        else:
            await update.message.reply_text("❌ Name / Email mismatch. Please try again or contact the office.")
    else:
        await update.message.reply_text("❌ Something went wrong. Please restart the registration process.")
    
    return ConversationHandler.END

async def handle_message(update: Update, context: CallbackContext):
    """Handles incoming messages."""
    user = update.message.from_user
    user_id = user.id
    name = f"{user.first_name} {user.last_name or ''}".strip()
    message = update.message.text.strip().lower()

    logger.info(f"📩 Message from {name} ({user_id}): {message}")

    # Registration trigger words
    if message in ["add me", "register", "sign up", "link account"]:
        return await start_registration(update, context)
    
    # Save to Airtable (for general messages)
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "records": [
            {
                "fields": {
                    "User ID": user_id,
                    "Name": name,
                    "Message": message,
                    "Timestamp": datetime.datetime.utcnow().isoformat()
                }
            }
        ]
    }
    response = requests.post(AIRTABLE_URL, json=data, headers=headers)

    if response.status_code == 200:
        await update.message.reply_text("✅ Your message has been saved!")
    else:
        await update.message.reply_text("❌ Failed to save your message.")

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Handles incoming Telegram updates (FIXED)."""
    try:
        json_data = request.get_json()
        logger.info(f"📩 Incoming Webhook Data: {json_data}")

        update = Update.de_json(json_data, bot_app.bot)

        # Process the update inside the event loop
        asyncio.run(bot_app.process_update(update))

        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"🚨 Webhook Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def home():
    return "Bot is running!"

def start_flask():
    """Runs the Flask server in a separate thread."""
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

def start_bot():
    """Starts the Telegram bot with webhook mode."""
    bot_app.add_handler(ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & filters.Regex("^(add me|register|sign up|link account)$"), start_registration)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_for_email)],
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, complete_registration)]
        },
        fallbacks=[]
    ))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_app.initialize())  
    loop.run_until_complete(set_webhook())  

    logger.info("✅ Webhook is ready. Running bot with Flask...")
    threading.Thread(target=start_flask).start()

if __name__ == "__main__":
    start_bot()
