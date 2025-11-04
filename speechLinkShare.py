import os
import time
# import speech_recognition as sr  
import pandas as pd
from datetime import datetime
# import asyncio                  
# import edge_tts                 
# import tempfile                 
# import pygame                   
import spacy
from textblob import TextBlob
import requests
from difflib import SequenceMatcher
from urllib.parse import quote

# Added FastAPI, Twilio, and Uvicorn imports 
import uvicorn
from fastapi import FastAPI, Form, Response, Query, Request
from twilio.twiml.voice_response import VoiceResponse, Gather

# Added imports for making outbound calls 
from twilio.rest import Client
from dotenv import load_dotenv
# 

#  NLP & Spacy 
nlp = spacy.load("en_core_web_sm")

#  Ollama text generation 
def ai_response(prompt, model_name="phi3:mini"):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "prompt": prompt},
            timeout=4
        )
        return response.json()["response"].strip()
    except Exception as e:
        print("Ollama Error:", e)
        return "I'm sorry, I didn’t catch that."

# Emotion detection
def detect_emotion(text):
    blob = TextBlob(text)
    s = blob.sentiment.polarity
    if s > 0.3:
        return "happy"
    elif s < -0.3:
        return "angry"
    return "neutral"

#  Load products 
def load_products():
    # Use absolute path to find products.xlsx 
    script_dir = os.path.dirname(os.path.abspath(__file__))
    excel_path = os.path.join(script_dir, "products.xlsx")
    
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Error: products.xlsx not found at {excel_path}")
        
    df = pd.read_excel(excel_path)
    df.columns = [c.strip().replace(" ", "_").lower() for c in df.columns]
    required_cols = ["product_name", "description", "price", "product_link"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column in Excel: '{col}'")
    products = df.to_dict(orient="records")
    print(f"Loaded {len(products)} products successfully from {excel_path}.")
    return products

#  Greeting 
def intro_message():
    return (
        "Hi there! I’m your sales agent from Creer Infotech. "
        "I’ve reached out to share some exciting offers on our latest products. "
        "Can I take a few minutes to tell you about them?"
    )

#  Keywords 
AFFIRMATIVE = ["yes", "ya", "yup", "sure", "ha", "haan", "okay", "ok", "of course", "why not", "alright"]
NEGATIVE = ["no", "nope", "not now", "not interested", "maybe later", "no thanks"]
CALL_KEYWORDS = ["call me", "talk to agent", "contact me", "speak to agent", "connect me to agent"]
# Moved INFO_KEYWORDS to global scope 
INFO_KEYWORDS = ["tell me more", "details", "more info", "specs", "specifications", "explain", "description", "features"]

#  SMS via HSP 
def send_sms_via_hsp(mobile_number, message):
    try:
        params = {
            "username": "cketul50", 
            "message": message,
            "sendername": "DASSAM", 
            "smstype":"TRANS",
            "numbers": str(mobile_number),
            "apikey": "6db4883a-60af-47d5-9541-96485056d5b2", 
            "templatename": "DASSAM"
        }
        response = requests.get("http://sms.hspsms.com/sendSMS", params=params)
        print("HSP SMS Response:", response.text)
    except Exception as e:
        print("Failed to send SMS via HSP:", e)

# This function was defined inside the loop, moved to global 
def similar(a, b): return SequenceMatcher(None, a, b).ratio()

# Moved offers list to global scope 
OFFERS_LIST = [
    "I completely understand! But before you go — we’re giving a 20% discount just for today. Would you like to take a quick look?",
    "Totally fair! But if I may — we’re offering free delivery on all products this week. Can I share a few top deals?",
    "I hear you! However, we’ve got a limited-time combo offer where you can save even more. Would you like to check that out?",
    "Alright! But trust me, this week’s festive sale is really something special — 25% off on bestsellers! Interested?",
    "Okay, I get it. Still, let me tell you — even browsing our collection could give you an idea for your next purchase. Shall I share a link?",
    "No problem at all! But just one last thing — we’re giving exclusive coupons for early customers today. Should I send one to you?"
]

# Load products once on server startup 
PRODUCTS_LIST = load_products()

# Use an absolute path for the log file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "Sales_Conversation_Twilio.xlsx")
print(f" ‼ Logging conversations to: {LOG_FILE} ‼ ")


# Helper function to log a turn in the conversation 
def log_turn(ai_question, user_response, emotion, ai_reply, phone_number):
    new_log = pd.DataFrame({
        "Question": [ai_question],
        "User_Response": [user_response],
        "Emotion": [emotion],
        "AI_Reply": [ai_reply],
        "PhoneNumber": [phone_number],
        "Timestamp": [datetime.now()]
    })
    try:
        # Check if openpyxl is installed 
        try:
            import openpyxl
        except ImportError:
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print("ERROR: 'openpyxl' library not found. Cannot write to Excel.")
            print("Please install it: pip install openpyxl")
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            return

        if os.path.exists(LOG_FILE):
            old = pd.read_excel(LOG_FILE)
            df_log = pd.concat([old, new_log], ignore_index=True)
        else:
            df_log = new_log
        
        # Save to the absolute path 
        df_log.to_excel(LOG_FILE, index=False)
        
    except Exception as e:
        # Make errors much more visible in the server log 
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"CRITICAL ERROR logging to Excel: {e}")
        print(f"Attempted to write to file: {LOG_FILE}")
        print("Please check file permissions.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

# FastAPI SERVER & TWILIO LOGIC START HERE 
app = FastAPI()

# This is the modified function to handle silence retries 
def create_twiml_response(
    text_to_say: str, 
    action_url: str, 
    speech_timeout: int = 5,  
    num_retries: int = 2      
):
    """
    Creates a TwiML response to <Say> text and then <Gather> (listen for) 
    the user's next response, sending it to the action_url.
    
    If the user is silent, it will re-prompt them `num_retries` times
    before finally hanging up.
    """
    response = VoiceResponse()

    #  First Attempt 
    gather = Gather(input="speech", speechTimeout=str(speech_timeout), action=action_url, method="POST")
    gather.say(text_to_say)
    response.append(gather)

    #  Retry Loop (if the first gather times out) 
    for i in range(num_retries):
        # This is the re-prompt message
        response.say("I'm sorry, I didn't hear a response. Are you still there?")
        
        # We create another <Gather> for the retry
        retry_gather = Gather(input="speech", speechTimeout=str(speech_timeout), action=action_url, method="POST")
        response.append(retry_gather)

    #  Final Fallback 
    response.say("Sorry we weren't able to hear you after the multiple times. Goodbye.")
    response.hangup()
    
    # Return as XML
    return Response(content=str(response), media_type="application/xml")

# This endpoint starts the call 
@app.post("/start-call")
def start_call(request: Request, From: str = Form(None), To: str = Form(None)):
    """
    This is the first endpoint Twilio calls. 
    It greets the user and listens for the first "yes" or "no".
    'From' is the user's phone number, passed by Twilio.
    """
    print(f" New Call Started from: {From}, To : {To}")
    
    # We pass the user's phone number in the state URL 
    user_phone = To if To else "Unknown"
    
    # State is passed in the URL: persuasion=0, explained=0, phone=...
    safe_phone = quote(user_phone)
    action_url = f"/handle-conversation?persuasion=0&explained=0&phone={safe_phone}"
    
    # Get the intro message
    intro = intro_message()
    
    # Log this first turn
    log_turn(ai_question="[Call Started]", user_response="", emotion="", ai_reply=intro, phone_number=user_phone)
    
    # Create the TwiML to speak the intro and listen for a reply
    return create_twiml_response(intro, action_url)

# This endpoint handles the entire conversation loop 
@app.post("/handle-conversation")
def handle_conversation(
    SpeechResult: str = Form(None),           
    persuasion: int = Query(0),               
    explained: int = Query(0),                
    phone: str = Query("Unknown")             
):
    """
    This is the main "loop". Twilio calls this endpoint every time
    the user speaks. We read the state (persuasion, explained, phone) from
    the URL, process the user's speech, and decide what to say next.
    """
    
    response = VoiceResponse()
    user_input = SpeechResult if SpeechResult else ""
    user_input_lower = user_input.lower().strip()
    emotion = detect_emotion(user_input)
    
    print(f"User ({phone}) said: {user_input} (Emotion: {emotion})")
    print(f"Current state: persuasion={persuasion}, explained={explained}")
    
    #  Convert state variables from int (0/1) to bool 
    product_explained = bool(explained)
    persuasion_used = persuasion
    
    ai_reply_text = "" 
    
    # We build the next URL, carrying the state forward 
    def build_next_url(pers, expl):
        safe_phone = quote(phone)
        return f"/handle-conversation?persuasion={pers}&explained={int(expl)}&phone={safe_phone}"

    #  Exit 
    if user_input_lower in ["exit", "quit", "stop", "bye", "ok bye", "goodbye"]:
        ai_reply_text = "Thank you for your time! Have a great day."
        response.say(ai_reply_text)
        response.hangup()
        log_turn("[Stateful check]", user_input, emotion, ai_reply_text, phone)
        return Response(content=str(response), media_type="application/xml")

    #  Handle NO with persuasion 
    if any(word in user_input_lower for word in NEGATIVE):
        persuasion_used += 1
        if persuasion_used <= len(OFFERS_LIST):
            ai_reply_text = OFFERS_LIST[persuasion_used - 1]
            # We update the state in the URL for the *next* turn 
            next_action_url = build_next_url(persuasion_used, product_explained)
            log_turn("[Persuasion check]", user_input, emotion, ai_reply_text, phone)
            return create_twiml_response(ai_reply_text, next_action_url)
        else:
            ai_reply_text = "No worries! Have a great day ahead."
            response.say(ai_reply_text)
            response.hangup()
            log_turn("[Persuasion check]", user_input, emotion, ai_reply_text, phone)
            return Response(content=str(response), media_type="application/xml")

    #  Handle YES (start product listing) 
    if any(word in user_input_lower for word in AFFIRMATIVE) and not product_explained:
        product_explained = True
        product_text = "Here are our latest offers:\n"
        for p in PRODUCTS_LIST:
            product_text += f"- {p['product_name']}\n"
        ai_reply_text = product_text + "\nWhich product would you like to purchase?"
        
        # Update state, explained is now True (1) 
        next_action_url = build_next_url(persuasion_used, product_explained)
        log_turn("[Intro response]", user_input, emotion, ai_reply_text, phone)
        return create_twiml_response(ai_reply_text, next_action_url)

    #  Handle CALL agent 
    if any(kw in user_input_lower for kw in CALL_KEYWORDS):
        current_hour = datetime.now().hour
        if 11 <= current_hour < 17:
            ai_reply_text = "Please wait until the agent is connected..."
            response.say(ai_reply_text)
            response.pause(length=3) 
            response.say("You are now connected to the agent. Ending the conversation. Thank you!")
            # response.dial("+1234567890")
            response.hangup()
        else:
            ai_reply_text = "Our agent will contact you later. Meanwhile, would you like to hear about our products?"
            #  We ask again, so we loop back to the same state 
            next_action_url = build_next_url(persuasion_used, product_explained)
            log_turn("[Agent check]", user_input, emotion, ai_reply_text, phone)
            return create_twiml_response(ai_reply_text, next_action_url)
        
        log_turn("[Agent check]", user_input, emotion, ai_reply_text, phone)
        return Response(content=str(response), media_type="application/xml")

    #  Handle Info request 
    if any(kw in user_input_lower for kw in INFO_KEYWORDS):
        found_product = None
        for p in PRODUCTS_LIST:
            if p["product_name"].lower() in user_input_lower:
                found_product = p
                break
        if found_product:
            ai_reply_text = (
                f"{found_product['product_name']} — {found_product['description']}. "
                f"The price is ₹{found_product['price']}. "
                f"You can check it out here: {found_product['product_link']}. "
                "Would you like to purchase it?"
            )
        else:
            ai_reply_text = "Could you please specify which product you want more details about?"
        
        #  Loop back, state doesn't change 
        next_action_url = build_next_url(persuasion_used, product_explained)
        log_turn("[Info request]", user_input, emotion, ai_reply_text, phone)
        return create_twiml_response(ai_reply_text, next_action_url)

    #  Match Product Name (This leads to an SMS and Hangup) 
    selected_product = None
    for p in PRODUCTS_LIST:
        name = p["product_name"].lower()
        if similar(name, user_input_lower) > 0.6 or any(word in user_input_lower for word in name.split()):
            selected_product = p
            break
            
    if selected_product:
        # Use the phone number from our state 
        mobile_number = phone 
        product_link = selected_product["product_link"]
        message = (
           f"{product_link} is your OTP for login into your account. GGISKB"
        )
        #  This still runs on your server, so it works! 
        send_sms_via_hsp(mobile_number, message) 
        
        last_digits = "".join(mobile_number[-4:])
        ai_reply_text = (
            f"Great choice! I’ve sent the link of {selected_product['product_name']} "
            f"to your phone number ending with {last_digits}. "
            "Thank you for your time! I really appreciate it."
        )
        response.say(ai_reply_text)
        response.hangup()
        log_turn("[Product match]", user_input, emotion, ai_reply_text, phone)
        return Response(content=str(response), media_type="application/xml")

    #  Fallback: AI Response (Ollama) or list products 
    # Using your original logic to list products as fallback 
    ai_reply_text = "Sorry, we don’t have that product right now."
    product_text = "Here are our latest offers:\n"
    for p in PRODUCTS_LIST:
        product_text += f"- {p['product_name']}: {p['description']} at ₹{p['price']}\n"
    ai_reply_text += "\n" + product_text + "\nWhich product would you like to purchase?"
    
    #  Loop back, state doesn't change 
    next_action_url = build_next_url(persuasion_used, product_explained)
    log_turn("[Fallback]", user_input, emotion, ai_reply_text, phone)
    return create_twiml_response(ai_reply_text, next_action_url)

# ENDPOINTS TO TRIGGER OUTBOUND CALLS

def _initiate_call(user_number: str):
    """Helper function to load env vars and make a single call."""
    load_dotenv()
    
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_number = os.getenv("TWILIO_NUMBER")
    ngrok_url = os.getenv("NGROK_URL")

    if not all([account_sid, auth_token, twilio_number, ngrok_url]):
        print(" ERROR: Missing .env variables ")
        return {"error": "Missing one or more .env variables (SID, TOKEN, TWILIO_NUMBER, NGROK_URL)"}

    try:
        start_call_url = f"{ngrok_url}/start-call"
        client = Client(account_sid, auth_token)

        print(f" Attempting to call: {user_number} ")
        call = client.calls.create(
            to=user_number,
            from_=twilio_number,
            url=start_call_url  
        )
        print(f"Successfully initiated call! SID: {call.sid}")
        return {"status": "Call initiated", "sid": call.sid, "to": user_number}

    except Exception as e:
        print(f" Error making call to {user_number}: {e} ")
        return {"status": "Failed", "error": str(e), "to": user_number}


@app.get("/start-outbound-call")
def start_outbound_call(phone: str):
    """
    Triggers a single outbound call.
    Test this in your browser: http://localhost:8000/start-outbound-call?phone=+1234567890
    (Use your real phone number with country code)
    """
    if not phone:
        return {"error": "You must provide a 'phone' query parameter."}
    
    return _initiate_call(phone)


@app.get("/start-excel-call-list")
def start_excel_call_list():
    """
    Reads 'call_list.xlsx' and calls every number in the 'phone' column.
    Test this in your browser: http://localhost:8000/start-excel-call-list
    """
    call_list_path = os.path.join(SCRIPT_DIR, "call_list.xlsx")
    if not os.path.exists(call_list_path):
        return {"error": "call_list.xlsx not found in script directory."}

    try:
        df = pd.read_excel(call_list_path)
        if "phone" not in df.columns:
            return {"error": "Excel file must have a 'phone' column."}
        
        phone_numbers = df["phone"].dropna().tolist()
        results = []
        
        print(f" Starting Excel Call List ({len(phone_numbers)} numbers) ")
        for number in phone_numbers:
            result = _initiate_call(str(number))
            results.append(result)
            time.sleep(1) # Add a small delay between calls
        
        print(" Excel Call List Finished ")
        return {"status": "Call list processed", "results": results}
        
    except Exception as e:
        return {"error": f"Failed to read Excel file: {str(e)}"}


#  ORIGINAL MAIN CONVERSATION 
# ... (all your commented-out original code is unchanged) ...

# This is how you run the new FastAPI server 
if __name__ == "__main__":
    # Check for openpyxl before starting 
    try:
        import openpyxl
    except ImportError:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("WARNING: 'openpyxl' not found. Excel logging will fail.")
        print("Please install it: pip install openpyxl")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        time.sleep(3) # Pause to make sure user sees the warning
        
    # Check for python-dotenv before starting 
    try:
        import dotenv
    except ImportError:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("WARNING: 'python-dotenv' not found. Outbound calls will fail.")
        print("Please install it: pip install python-dotenv")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        time.sleep(3) # Pause to make sure user sees the warning

    print(" Starting FastAPI server for Twilio ")
    print(f" Log file will be saved at: {LOG_FILE} ")
    print(" Your server will be at http://localhost:8000 ")
    print(" Your first Twilio webhook URL will be http://<your_ngrok_url>/start-call ")
    print("\n Outbound Call Endpoints ")
    print("Call a single number: http://localhost:8000/start-outbound-call?phone=NUMBER_TO_CALL")
    print("Call from Excel list: http://localhost:8000/start-excel-call-list")
    uvicorn.run(app, host="0.0.0.0", port=8000)