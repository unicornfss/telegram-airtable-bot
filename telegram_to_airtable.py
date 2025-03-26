import os
import requests
import datetime
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CommandHandler, CallbackContext
from flask import Flask, request, jsonify
import threading

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TABLE_NAME = "Instructor"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Airtable API URL
AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"

# Flask app for handling webhook
app = Flask(__name__)

# Telegram bot application
bot_app = Application.builder().token(TOKEN).build()

# Store user registration states
user_states = {}

async def set_webhook():
    """Sets the webhook for Telegram Bot."""
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"✅ Webhook set: {WEBHOOK_URL}/webhook")
    else:
        logger.error("❌ ERROR: WEBHOOK_URL is missing!")

def search_airtable(field, value):
    """Searches Airtable for a matching record."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"filterByFormula": f"{{{field}}} = '{value}'"}
    response = requests.get(AIRTABLE_URL, headers=headers, params=params)
    if response.status_code == 200:
        records = response.json().get("records", [])
        return records[0] if records else None
    return None

def update_airtable(record_id, telegram_id):
    """Updates Airtable with the Telegram ID."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"records": [{"id": record_id, "fields": {"Telegram ID": telegram_id}}]}
    response = requests.patch(AIRTABLE_URL, json=data, headers=headers)
    return response.status_code == 200

async def handle_message(update: Update, context: CallbackContext):
    """Handles incoming messages."""
    user_id = update.message.from_user.id
    message = update.message.text.strip()
    chat_id = update.message.chat_id
    
    logger.info(f"📩 Message from {user_id}: {message}")
    
    if user_id in user_states:
        step = user_states[user_id]['step']
        if step == "awaiting_name":
            record = search_airtable("Name", message)
            if record:
                user_states[user_id]['record_id'] = record['id']
                user_states[user_id]['step'] = "awaiting_email"
                await update.message.reply_text("✅ Name found! Now, please enter your email.")
            else:
                await update.message.reply_text("❌ Name not found in database, please contact office.")
                del user_states[user_id]
        elif step == "awaiting_email":
            record = search_airtable("Email", message)
            if record and record['id'] == user_states[user_id]['record_id']:
                success = update_airtable(record['id'], str(user_id))
                if success:
                    await update.message.reply_text("✅ Registration complete! Your Telegram ID is now linked.")
                else:
                    await update.message.reply_text("❌ Failed to update database. Contact support.")
                del user_states[user_id]
            else:
                await update.message.reply_text("❌ Name/Email mismatch, please try again or contact office.")
                del user_states[user_id]
        return
    
    if message.lower() in ["add me", "register", "link", "signup"]:
        user_states[user_id] = {"step": "awaiting_name"}
        await update.message.reply_text("🔍 Please enter your full name as in the database.")
    else:
        await update.message.reply_text("ℹ️ Send 'add me' or 'register' to link your Telegram ID.")

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Handles incoming Telegram updates."""
    try:
        json_data = request.get_json()
        logger.info(f"📩 Incoming Webhook Data: {json_data}")
        update = Update.de_json(json_data, bot_app.bot)
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
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_app.initialize())
    loop.run_until_complete(set_webhook())
    logger.info("✅ Webhook is ready. Running bot with Flask...")
    threading.Thread(target=start_flask).start()

if __name__ == "__main__":
    start_bot()
