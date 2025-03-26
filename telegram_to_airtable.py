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
INSTRUCTOR_TABLE = "Instructor"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Airtable API URLs
AIRTABLE_MESSAGES_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
AIRTABLE_INSTRUCTORS_URL = f"https://api.airtable.com/v0/{BASE_ID}/{INSTRUCTOR_TABLE}"

# Flask app for handling webhook
app = Flask(__name__)

# Telegram bot application
bot_app = Application.builder().token(TOKEN).build()


async def set_webhook():
    """Sets the webhook for Telegram Bot."""
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"✅ Webhook set: {WEBHOOK_URL}/webhook")
    else:
        logger.error("❌ ERROR: WEBHOOK_URL is missing!")


def save_to_airtable(user_id, name, message):
    """Saves messages to Airtable and logs the response for debugging."""
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
        response = requests.post(AIRTABLE_MESSAGES_URL, json=data, headers=headers)
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


def find_instructor(name=None, email=None):
    """Find an instructor by name or email."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    
    filter_formula = []
    if name:
        filter_formula.append(f"{{Name}}='{name}'")
    if email:
        filter_formula.append(f"{{Email}}='{email}'")

    filter_query = "AND(" + ",".join(filter_formula) + ")" if filter_formula else ""
    
    response = requests.get(AIRTABLE_INSTRUCTORS_URL, headers=headers, params={"filterByFormula": filter_query})
    records = response.json().get("records", [])
    
    return records[0] if records else None


def update_instructor_telegram_id(record_id, telegram_id):
    """Updates an instructor's Telegram ID."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "records": [
            {"id": record_id, "fields": {"Telegram ID": str(telegram_id)}}
        ]
    }
    response = requests.patch(AIRTABLE_INSTRUCTORS_URL, json=data, headers=headers)
    return response.status_code == 200


async def handle_message(update: Update, context: CallbackContext):
    """Handles incoming messages."""
    try:
        user = update.message.from_user
        user_id = user.id
        name = f"{user.first_name} {user.last_name or ''}".strip()
        message = update.message.text.strip().lower()

        logger.info(f"📩 Message from {name} ({user_id}): {message}")

        # Registration Process
        if message in ["add me", "register"]:
            await update.message.reply_text("📝 Please send your full name as registered in the system.")
            context.user_data["registration_step"] = "awaiting_name"
            return

        if "registration_step" in context.user_data:
            step = context.user_data["registration_step"]

            if step == "awaiting_name":
                context.user_data["name"] = message
                instructor = find_instructor(name=message)

                if not instructor:
                    await update.message.reply_text("❌ Name not found in database. Please contact the office.")
                    del context.user_data["registration_step"]
                    return

                context.user_data["registration_step"] = "awaiting_email"
                context.user_data["instructor_id"] = instructor["id"]
                await update.message.reply_text("📧 Please send your registered email address.")
                return

            if step == "awaiting_email":
                instructor_id = context.user_data["instructor_id"]
                instructor = find_instructor(email=message)

                if not instructor or instructor["id"] != instructor_id:
                    await update.message.reply_text("❌ Name / Email mismatch. Please try again or contact the office.")
                    del context.user_data["registration_step"]
                    return

                if update_instructor_telegram_id(instructor_id, user_id):
                    await update.message.reply_text("✅ Registration successful! You are now linked with Telegram.")
                else:
                    await update.message.reply_text("❌ Failed to update Telegram ID. Please contact the office.")

                del context.user_data["registration_step"]
                return

        # Save messages to Airtable
        status = save_to_airtable(user_id, name, message)
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
