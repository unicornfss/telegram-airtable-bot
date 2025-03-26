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
TABLE_NAME = "Telegram messages"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Airtable API URL
AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"

# Flask app for handling webhook
app = Flask(__name__)

# Telegram bot application (properly initialized)
bot_app = Application.builder().token(TOKEN).build()


async def set_webhook():
    """Sets the webhook for Telegram Bot."""
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"✅ Webhook set: {WEBHOOK_URL}/webhook")
    else:
        logger.error("❌ ERROR: WEBHOOK_URL is missing!")


def save_to_airtable(user_id, name, message):
    """Saves messages to Airtable."""
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
                    "Timestamp": datetime.datetime.now().isoformat()
                }
            }
        ]
    }
    response = requests.post(AIRTABLE_URL, json=data, headers=headers)
    return response.status_code


async def handle_message(update: Update, context: CallbackContext):
    """Handles incoming messages."""
    user = update.message.from_user
    user_id = user.id
    name = f"{user.first_name} {user.last_name or ''}".strip()
    message = update.message.text

    logger.info(f"📩 Message from {name} ({user_id}): {message}")

    # Save to Airtable
    status = save_to_airtable(user_id, name, message)

    if status == 200:
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


import asyncio

def start_bot():
    """Starts the Telegram bot with webhook mode."""
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ✅ Initialize inside the existing event loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_app.initialize())  
    loop.run_until_complete(set_webhook())  # Set the webhook properly

    logger.info("✅ Webhook is ready. Running bot with Flask...")
    threading.Thread(target=start_flask).start()


