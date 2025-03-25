import os
import requests
import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CommandHandler, CallbackContext

# Get environment variables (used when deploying)
TOKEN = "7899090667:AAHQIvcXTi6BwMOhjXU6vrmpcfWy7Y0WcuE"
AIRTABLE_API_KEY = os.getenv("pate0GC1BzjAGkDSy.0efd2d0e5b409a02b09f2b36a84cb6c7db5f15da73088d49af5408fa3c93dff8")
BASE_ID = os.getenv("appzlZFE8pqIu8fOi")
TABLE_NAME = "Telegram messages"  # Ensure this matches your Airtable table name

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

# Function to start the bot
def main():
    print(f"DEBUG: Telegram Bot Token is {TOKEN}")
    app = Application.builder().token(TOKEN).build()

    # Add handler for text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
