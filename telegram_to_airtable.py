import os
import requests
import datetime
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
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
INSTRUCTOR_TABLE = "Instructor"  # Instructor table for registration
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Airtable API URLs
AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
INSTRUCTOR_URL = f"https://api.airtable.com/v0/{BASE_ID}/{INSTRUCTOR_TABLE}"

# Flask app for handling webhook
app = Flask(__name__)

# Telegram bot application
bot_app = Application.builder().token(TOKEN).build()

# Store user registration steps
user_states = {}


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
                    "User ID": f"{user_id}",
                    "Name": name,
                    "Message": message,
                    "Timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
                }
            }
        ]
    }

    try:
        response = requests.post(AIRTABLE_URL, json=data, headers=headers)
        response_json = response.json()
        if response.status_code == 200:
            logger.info(f"✅ Airtable Save Successful: {response_json}")
            return 200
        else:
            logger.error(f"❌ Airtable Save Failed! Status: {response.status_code}, Response: {response_json}")
            return response.status_code
    except Exception as e:
        logger.error(f"🚨 Airtable Request Exception: {e}")
        return 500


def lookup_instructor(name):
    """Checks if the instructor exists in Airtable (case-insensitive match)."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    # Airtable filter formula (escaping single quotes)
    formula = f"FIND(LOWER('{name}'), LOWER({{Name}})) > 0"
    url = f"{INSTRUCTOR_URL}?filterByFormula={formula}"
    
    response = requests.get(url, headers=headers)
    data = response.json()

    if "records" in data and len(data["records"]) > 0:
        return data["records"][0]  # Return the first match
    return None



def update_instructor_telegram_id(record_id, telegram_id):
    """Updates the instructor's Telegram ID in Airtable."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {"records": [{"id": record_id, "fields": {"Telegram ID": str(telegram_id)}}]}
    response = requests.patch(INSTRUCTOR_URL, json=data, headers=headers)
    return response.status_code == 200


async def handle_message(update: Update, context: CallbackContext):
    """Handles incoming messages."""
    try:
        user = update.message.from_user
        user_id = user.id
        message = update.message.text.strip().lower()

        logger.info(f"📩 Message from {user_id}: {message}")

        # **Registration Process**
        if user_id in user_states:
            step = user_states[user_id]["step"]

            if step == "ask_name":
                instructor = lookup_instructor(message)
                if instructor:
                    user_states[user_id] = {"step": "ask_email", "name": message, "record_id": instructor["id"]}
                    await update.message.reply_text("✅ Name found! Please send your email address.")
                else:
                    await update.message.reply_text("❌ Name not found in database. Please contact the office.")
                    del user_states[user_id]
                return

            if step == "ask_email":
                record_id = user_states[user_id]["record_id"]
                name = user_states[user_id]["name"]
                instructor = lookup_instructor(name)

                if instructor and instructor["fields"].get("Email", "").lower() == message.lower():
                    if update_instructor_telegram_id(record_id, user_id):
                        await update.message.reply_text("✅ Registration complete! Your Telegram ID has been saved.")
                    else:
                        await update.message.reply_text("❌ Failed to save your Telegram ID. Try again later.")
                else:
                    await update.message.reply_text("❌ Name / Email mismatch. Please try again or contact office.")

                del user_states[user_id]
                return

        # **Check for "register" or "add me"**
        if message in ["register", "add me", "signup", "join"]:
            user_states[user_id] = {"step": "ask_name"}
            await update.message.reply_text("🔹 Please send your full name as it appears in our database.")
            return

        # **Save all other messages to Airtable**
        status = save_to_airtable(user_id, user.first_name, message)

        if status == 200:
            await update.message.reply_text("✅ Your message has been saved!")
        else:
            await update.message.reply_text("❌ Failed to save your message.")

    except Exception as e:
        logger.error(f"🚨 Message Handling Error: {e}")


@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Handles incoming Telegram updates safely."""
    try:
        json_data = request.get_json()
        logger.info(f"📩 Incoming Webhook Data: {json_data}")

        update = Update.de_json(json_data, bot_app.bot)

        # **Properly handle the event loop**
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(bot_app.process_update(update))

        return jsonify({"status": "success"}), 200
    except Exception as e:
        logger.error(f"🚨 Webhook Processing Error: {e}")
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
    try:
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(bot_app.initialize())
        loop.run_until_complete(set_webhook())

        logger.info("✅ Webhook is ready. Running bot with Flask...")
        threading.Thread(target=start_flask, daemon=True).start()

        loop.run_forever()

    except Exception as e:
        logger.error(f"🚨 Bot Startup Error: {e}")


if __name__ == "__main__":
    start_bot()
