import os
import requests
import datetime
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
from flask import Flask, request
import threading

# Get environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TABLE_NAME = "Telegram messages"

# Airtable API URL
AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"

# ✅ Create a global asyncio event loop
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Initialize the bot application
app = Application.builder().token(TOKEN).build()

# ✅ Function to save messages to Airtable
def save_to_airtable(user_id, name, message):
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

# ✅ Function to handle incoming messages
async def handle_message(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = user.id
    name = f"{user.first_name} {user.last_name or ''}".strip()
    message = update.message.text

    print(f"📩 New Message Received: {message} from {name} (ID: {user_id})")

    # Save to Airtable
    status = save_to_airtable(user_id, name, message)

    if status == 200:
        print("✅ Message saved to Airtable!")
        await update.message.reply_text("✅ Your message has been saved!")
    else:
        print("❌ Airtable save failed!")
        await update.message.reply_text("❌ Failed to save your message.")


# ✅ Function to set up the webhook
async def set_webhook():
    if WEBHOOK_URL:
        await app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        print(f"✅ Webhook set: {WEBHOOK_URL}/webhook")
    else:
        print("❌ ERROR: WEBHOOK_URL is missing!")

def start_bot():
    print("🚀 Starting bot...")

    # Add handler for text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ✅ Ensure there's a running event loop
    loop.run_until_complete(set_webhook())

    print("✅ Webhook is ready. Running bot with Flask...")

# ✅ Flask app to handle web requests
flask_app = Flask(__name__)

@flask_app.route('/', methods=['GET'])
def home():
    return "Bot is running!"

@flask_app.route('/webhook', methods=['POST'])
@flask_app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """ Handle incoming Telegram messages via webhook """
    data = request.get_json()
    print(f"🔍 Received Webhook Data: {data}")  # Debugging log

    try:
        update = Update.de_json(data, app.bot)

        # ✅ Process updates inside the event loop
        loop.create_task(app.process_update(update))

        return "OK", 200
    except Exception as e:
        print(f"❌ Webhook Processing Error: {e}")  # Debugging log
        return "Error", 500


def run_flask():
    port = int(os.getenv("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    start_bot()
