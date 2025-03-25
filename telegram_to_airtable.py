import os
import requests
import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
from flask import Flask
import threading

# Get environment variables securely
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TABLE_NAME = "Telegram messages"

# Airtable API URL
AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"

# Function to save messages to Airtable
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

# Function to handle incoming messages
async def handle_message(update: Update, context: CallbackContext):
    user = update.message.from_user
    user_id = user.id
    name = f"{user.first_name} {user.last_name or ''}".strip()
    message = update.message.text

    # Save the message in Airtable
    status = save_to_airtable(user_id, name, message)

    if status == 200:
        await update.message.reply_text("✅ Your message has been saved!")
    else:
        await update.message.reply_text("❌ Failed to save your message.")

# Function to set up the Telegram webhook
async def set_webhook(application):
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=WEBHOOK_URL)
        print(f"✅ Webhook set: {WEBHOOK_URL}")
    else:
        print("❌ ERROR: WEBHOOK_URL is missing!")

# Function to start the bot using webhooks
def main():
    print("🚀 Starting bot...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Set webhook and start webhook listener
   import asyncio
    asyncio.run(set_webhook(app))

    app.run_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", 8080)), webhook_url=WEBHOOK_URL)

# Fake web server for Render (required to avoid port errors)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    main()
