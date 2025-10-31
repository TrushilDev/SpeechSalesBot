import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Twilio credentials
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
twilio_number = os.getenv("TWILIO_PHONE_NUMBER")  # Your Twilio trial number
destination_number = os.getenv("DESTINATION_NUMBER")  # Verified number to call

client = Client(account_sid, auth_token)

try:
    call = client.calls.create(
        twiml='<Response><Say>Hello! This is a test call from Twilio.</Say></Response>',
        to=destination_number,
        from_=twilio_number
    )
    print(f"✅ Call initiated! Call SID: {call.sid}")
except Exception as e:
    print("❌ Twilio Call Error:", e)
