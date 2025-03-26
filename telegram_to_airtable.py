import os
import requests
import datetime
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
from flask import Flask
import threading

# Get environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TABLE_NAME = "Telegram messages"

# Function to set up the webhook
async def set_webhook(application):
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=WEBHOOK_URL)
        print(f"✅ Webhook set: {WEBHOOK_URL}")
    else:
        print("❌ ERROR: WEBHOOK_URL is missing!")

def main():
    print("🚀 Starting bot...")
    app = Application.builder().token(TOKEN).build()

    # Add handler for text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ✅ Move this line **AFTER** defining `app`
    asyncio.run(set_webhook(app))

    print("✅ Webhook is ready. Running bot with Flask...")
    app.run_webhook(
    listen="0.0.0.0",
    port=int(os.getenv("PORT", 8080)),
    webhook_url=f"{WEBHOOK_URL}/webhook"
)


# Fake web server to avoid Render errors
flask_app = Flask(__name__)

@flask_app.route('/', methods=['GET'])
def home():
    return "Bot is running!"

@flask_app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    """ Handle incoming Telegram messages via webhook """
    update = Update.de_json(await flask_app.request.get_json(), bot)
    await app.process_update(update)
    return "OK", 200


def run_flask():
    port = int(os.getenv("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    main()
