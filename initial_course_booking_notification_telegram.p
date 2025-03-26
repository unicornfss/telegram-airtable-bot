import os
import requests
import time
import logging

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TABLE_NAME = "Bookings"

# Airtable API URL
AIRTABLE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"

# Telegram API URL
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def fetch_bookings_to_notify():
    """Fetches bookings that need a Telegram notification."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {
        "filterByFormula": 'AND({Send notification to instructor} = TRUE, {Course status} = "Scheduled", {Instructor Telegram ID} != "")'
    }

    response = requests.get(AIRTABLE_URL, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get("records", [])
    else:
        logger.error(f"❌ Failed to fetch bookings: {response.json()}")
        return []


def send_telegram_message(chat_id, message):
    """Sends a Telegram message to the instructor."""
    data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    response = requests.post(TELEGRAM_API_URL, json=data)

    if response.status_code == 200:
        logger.info(f"📨 Message sent to {chat_id}")
        return True
    else:
        logger.error(f"❌ Failed to send message: {response.json()}")
        return False


def process_notifications():
    """Processes notifications and sends Telegram messages."""
    bookings = fetch_bookings_to_notify()
    if not bookings:
        logger.info("✅ No pending Telegram notifications.")
        return

    for booking in bookings:
        fields = booking.get("fields", {})
        instructor_telegram_id = fields.get("Instructor Telegram ID")

        if not instructor_telegram_id:
            continue  # Skip if no Telegram ID is found

        # Extract relevant details
        course_name = fields.get("Course", "Unknown Course")
        start_date = fields.get("Start date", "Unknown Date")
        duration = fields.get("Course duration", "N/A")
        business = fields.get("Business", "Unknown Business")
        location = fields.get("Location name", "Unknown Location")
        address = fields.get("Address", "No Address Provided")
        fee = fields.get("Instructor fee", "N/A")
        contact_email = fields.get("Contact email", "No Contact")
        google_maps_url = fields.get("Google maps URL", "")

        # Format the message
        message = f"""📢 *New Course Assigned*
📌 *Course:* {course_name}
📅 *Start Date:* {start_date}
⏳ *Duration:* {duration} days
🏢 *Business:* {business}
📍 *Location:* {location}
🏠 *Address:* {address}
💰 *Instructor Fee:* {fee}
📧 *Admin Contact:* {contact_email}

🌍 [View Location on Google Maps]({google_maps_url})""" if google_maps_url else ""

        # Send the message
        if send_telegram_message(instructor_telegram_id, message):
            # Mark notification as sent in Airtable
            update_url = f"{AIRTABLE_URL}/{booking['id']}"
            update_data = {"fields": {"Send notification to instructor": False}}
            requests.patch(update_url, json=update_data, headers={"Authorization": f"Bearer {AIRTABLE_API_KEY}"})

        time.sleep(1)  # Avoid rate limits


if __name__ == "__main__":
    logger.info("🔄 Starting Telegram Notification Script...")
    while True:
        process_notifications()
        time.sleep(30)  # Check for new notifications every 30 seconds
