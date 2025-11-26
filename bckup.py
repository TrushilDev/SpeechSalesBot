import os
import time
import pandas as pd
from datetime import datetime
import spacy
from textblob import TextBlob
import requests
from difflib import SequenceMatcher
from urllib.parse import quote
import uvicorn
from fastapi import FastAPI, Form, Response, Query, Request, BackgroundTasks
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from dotenv import load_dotenv

#  NLP & Spacy 
nlp = spacy.load("en_core_web_sm")

# model alias used for translation 
OLLAMA_MODEL = "gemma2:9b-q4_K_M"

# translate any English text to Hindi 
def translate_to_hindi(text: str) -> str:
    """
    Translate English to natural, conversational Hindi for phone calls.
    If translation fails, returns original English text.
    """
    prompt = (
        "Translate the following English text into natural spoken Hindi for a phone call. "
        "Keep it concise and friendly. Do not add extra words.\n\n"
        f"English: {text}\n\nHindi:"
    )
    try:
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt},
            timeout=15
        )
        return r.json().get("response", "").strip() or text
    except Exception as e:
        print("Translation error:", e)
        return text

# prefer Gemma2 9B quantized for any generation 
def ai_response(prompt, model_name=OLLAMA_MODEL):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "prompt": prompt},
            timeout=15
        )
        return response.json().get("response","").strip() or "I'm sorry, I didn’t catch that."
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

#  Load products from Excel 
def load_products():
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

# dynamic English greeting to Hindi at runtime
def intro_message():
    hr = datetime.now().hour
    if 5 <= hr < 12:
        greet_en = "Good morning!"
    elif 12 <= hr < 17:
        greet_en = "Good afternoon!"
    elif 17 <= hr < 21:
        greet_en = "Good evening!"
    else:
        greet_en = "Hello!"
    base_greeting_en = (
        f"{greet_en} I am your sales agent from Creer Infotech. "
        "Would you like to hear about our latest products?"
    )
    return translate_to_hindi(base_greeting_en)

# keep all keywords in English/Hinglish 
AFFIRMATIVE = ["yes", "ya", "yup", "sure", "ha", "haan", "han", "ok", "okay", "of course", "why not", "alright", "theek", "thik", "thik hai", "हाँ", "ठीक", "ठीक है"]
NEGATIVE = ["no", "nope", "not now", "not interested", "maybe later", "no thanks", "nah", "nahi", "नहीं", "रुचि नहीं"]
CALL_KEYWORDS = ["call me", "talk to agent", "contact me", "speak to agent", "connect me to agent", "agent", "एजेंट", "कॉल", "बात कराएँ"]

INFO_KEYWORDS = ["tell me more", "details", "more info", "specs", "specifications", "explain", "description", "features", "जानकारी", "विवरण", "डिटेल"]

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

def similar(a, b): 
    return SequenceMatcher(None, a, b).ratio()

#  persuasion lines kept in ENGLISH. .
OFFERS_LIST_EN = [
    "I understand, but today we are offering a 20% discount. Would you like to quickly check the products?",
    "Totally fine, but we also have free delivery this week. Interested?",
    "We have a special combo offer today that can save you more. Shall I show the products?",
    "We are also running a festive sale this week. Would you like to take a quick look?",
    "Just a suggestion: browsing our items might help you decide. Should I continue?",
    "We are giving special coupons to early customers today. Would you like one?"
]

# Load products once
PRODUCTS_LIST = load_products()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "Sales_Conversation_Twilio.xlsx")
print(f" ‼ Logging conversations to: {LOG_FILE} ‼ ")

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
        try:
            import openpyxl
        except ImportError:
            print("ERROR: 'openpyxl' not found. pip install openpyxl")
            return

        if os.path.exists(LOG_FILE):
            old = pd.read_excel(LOG_FILE)
            df_log = pd.concat([old, new_log], ignore_index=True)
        else:
            df_log = new_log
        df_log.to_excel(LOG_FILE, index=False)
        print(f"--- Logged turn for {phone_number} ---")
    except Exception as e:
        print(f"CRITICAL ERROR logging to Excel: {e}  (file: {LOG_FILE})")

app = FastAPI()

#  all TTS will be Hindi; speech input language hi-IN
def create_twiml_response(
    text_to_say_hindi: str, 
    action_url: str, 
    speech_timeout: int = 7,  
    num_retries: int = 2,
    language: str = "hi-IN"
):
    """
    Says the provided Hindi text and gathers speech in hi-IN.
    Retries if silent.
    """
    response = VoiceResponse()

    # First attempt
    gather = Gather(
        input="speech", language=language, speechTimeout=str(speech_timeout),
        action=action_url, method="POST"
    )
    gather.say(text_to_say_hindi, voice="Polly.Aditi")
    response.append(gather)

    # Retries
    retry_msg_en = "Sorry, I could not hear you clearly. Could you please say it again?"
    retry_msg_hi = translate_to_hindi(retry_msg_en)
    for _ in range(num_retries):
        response.say(retry_msg_hi, voice="Polly.Aditi")
        retry_gather = Gather(
            input="speech", language=language, speechTimeout=str(speech_timeout),
            action=action_url, method="POST"
        )
        response.append(retry_gather)

    final_retry_en = "Sorry, we could not hear you even after several attempts. Goodbye."
    final_retry_hi = translate_to_hindi(final_retry_en)
    response.say(final_retry_hi, voice="Polly.Aditi")
    response.hangup()
    return Response(content=str(response), media_type="application/xml")

# Helper: build next state URL
def build_next_url(pers, expl, phone):
    safe_phone = quote(phone)
    return f"/handle-conversation?persuasion={pers}&explained={int(expl)}&phone={safe_phone}"

# Start call
@app.post("/start-call")
def start_call(request: Request, From: str = Form(None), To: str = Form(None)):
    print(f" New Call Started from: {From}, To : {To}")
    user_phone = To if To else (From if From else "Unknown")

    action_url = build_next_url(0, 0, user_phone)

    # dynamic English -> translated to Hindi
    intro_hi = intro_message()

    log_turn(ai_question="[Call Started]", user_response="", emotion="", ai_reply=intro_hi, phone_number=user_phone)
    return create_twiml_response(intro_hi, action_url)

# Main conversation loop
@app.post("/handle-conversation")
def handle_conversation(
    background_tasks: BackgroundTasks,
    SpeechResult: str = Form(None),
    persuasion: int = Query(0),
    explained: int = Query(0),
    phone: str = Query("Unknown")
):
    response = VoiceResponse()
    product_explained = bool(explained)
    persuasion_used = persuasion

    # Silence handling
    if SpeechResult is None or (isinstance(SpeechResult, str) and SpeechResult.strip() == ""):
        retry_hi = translate_to_hindi("Sorry, I couldn't hear you clearly. Could you please say that again?")
        next_action_url = build_next_url(persuasion_used, product_explained, phone)
        background_tasks.add_task(log_turn, "[No speech detected]", "", "", retry_hi, phone)
        return create_twiml_response(retry_hi, next_action_url)

    user_input = SpeechResult.strip()
    user_input_lower = user_input.lower()
    emotion = detect_emotion(user_input)

    print(f"User ({phone}) said: {user_input} (Emotion: {emotion})")
    print(f"Current state: persuasion={persuasion_used}, explained={product_explained}")

    def next_url():
        return build_next_url(persuasion_used, product_explained, phone)

    # Exit
    if user_input_lower in ["exit", "quit", "stop", "bye", "ok bye", "goodbye", "अलविदा", "बाय"]:
        bye_hi = translate_to_hindi("Thank you for your time. Goodbye!")
        response.say(bye_hi, voice="Polly.Aditi")
        response.hangup()
        background_tasks.add_task(log_turn, "[Exit]", user_input, emotion, bye_hi, phone)
        return Response(content=str(response), media_type="application/xml")

    # Handle NO with persuasion (up to 6)
    if any(word in user_input_lower for word in NEGATIVE):
        persuasion_used += 1
        if persuasion_used <= len(OFFERS_LIST_EN):
            offer_hi = translate_to_hindi(OFFERS_LIST_EN[persuasion_used - 1])
            background_tasks.add_task(log_turn, "[Persuasion]", user_input, emotion, offer_hi, phone)
            return create_twiml_response(offer_hi, build_next_url(persuasion_used, product_explained, phone))
        else:
            end_hi = translate_to_hindi("No problem. Have a great day!")
            response.say(end_hi, voice="Polly.Aditi")
            response.hangup()
            background_tasks.add_task(log_turn, "[Persuasion end]", user_input, emotion, end_hi, phone)
            return Response(content=str(response), media_type="application/xml")

    # Handle YES → list products once
    if any(word in user_input_lower for word in AFFIRMATIVE) and not product_explained:
        product_explained = True
        # Build English text then translate
        product_text_en = "Here are our available products:\n"
        for i, p in enumerate(PRODUCTS_LIST, start=1):
            product_text_en += f"{i}. {p['product_name']}\n"
        ask_en = "Please speak the name of the product you are interested in."
        ai_reply_hi = translate_to_hindi(product_text_en + ask_en)
        background_tasks.add_task(log_turn, "[Show products]", user_input, emotion, ai_reply_hi, phone)
        return create_twiml_response(ai_reply_hi, next_url())

    # Agent request
    if any(kw in user_input_lower for kw in CALL_KEYWORDS):
        hr = datetime.now().hour
        if 11 <= hr < 17:
            say_hi = translate_to_hindi("Please wait while I connect you to an agent...")
            response.say(say_hi, voice="Polly.Aditi")
            response.pause(length=2)
            done_hi = translate_to_hindi("Connecting you to the agent. Thank you!")
            response.say(done_hi, voice="Polly.Aditi")
            # response.dial("+911234567890")  # hook your agent
            response.hangup()
            background_tasks.add_task(log_turn, "[Agent connect]", user_input, emotion, say_hi, phone)
            return Response(content=str(response), media_type="application/xml")
        else:
            later_hi = translate_to_hindi("Our agent will call you soon. Meanwhile, would you like me to tell you about our products?")
            background_tasks.add_task(log_turn, "[Agent later]", user_input, emotion, later_hi, phone)
            return create_twiml_response(later_hi, next_url())

    # Info request → try exact product
    if any(kw in user_input_lower for kw in INFO_KEYWORDS):
        found_product = None
        for p in PRODUCTS_LIST:
            if p["product_name"].lower() in user_input_lower:
                found_product = p
                break
        if found_product:
            eng = (
                f"{found_product['product_name']} — {found_product['description']}. "
                f"The price is ₹{found_product['price']}. "
                f"Here is the link: {found_product['product_link']}. "
                "Would you like to purchase it?"
            )
            ai_reply_hi = translate_to_hindi(eng)
        else:
            names = ", ".join([p["product_name"] for p in PRODUCTS_LIST])
            ai_reply_hi = translate_to_hindi(
                f"Sorry, we don't have that product. We have: {names}. Which one would you like to know about?"
            )
        background_tasks.add_task(log_turn, "[Info request]", user_input, emotion, ai_reply_hi, phone)
        return create_twiml_response(ai_reply_hi, next_url())

    # Product name match (send link & end call)
    selected_product = None
    for p in PRODUCTS_LIST:
        name = p["product_name"].lower()
        if similar(name, user_input_lower) > 0.6 or any(word in user_input_lower for word in name.split()):
            selected_product = p
            break

    if selected_product:
        mobile_number = phone 
        product_link = selected_product["product_link"]

        # toggle this to False if you want English SMS
        SMS_IN_HINDI = True
        if SMS_IN_HINDI:
            sms_text = translate_to_hindi(f"Here is the link for {selected_product['product_name']}: {product_link}\n-Creer Infotech")
        else:
            sms_text = f"Here is the link for {selected_product['product_name']}: {product_link}\n-Creer Infotech"

        send_sms_via_hsp(mobile_number, sms_text)
        
        last_digits = "".join(mobile_number[-4:]) if isinstance(mobile_number, str) else ""
        thanks_en = (
            f"Great! I have sent the link for {selected_product['product_name']} "
            f"to your number ending with {last_digits}. Thank you for your time!"
        )
        thanks_hi = translate_to_hindi(thanks_en)

        response.say(thanks_hi, voice="Polly.Aditi")
        response.hangup()
        background_tasks.add_task(log_turn, "[Product match -> SMS sent]", user_input, emotion, thanks_hi, phone)
        return Response(content=str(response), media_type="application/xml")

    # Fallback: restrict to catalog, apologize + list (EN -> HI)
    names = ", ".join([p["product_name"] for p in PRODUCTS_LIST])
    fallback_en = f"Sorry, we don't have that product. Available products are: {names}. Which one would you prefer?"
    fallback_hi = translate_to_hindi(fallback_en)
    background_tasks.add_task(log_turn, "[Fallback]", user_input, emotion, fallback_hi, phone)
    return create_twiml_response(fallback_hi, next_url())

# ENDPOINTS TO TRIGGER OUTBOUND CALLS

def _initiate_call(user_number: str):
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
    if not phone:
        return {"error": "You must provide a 'phone' query parameter."}
    return _initiate_call(phone)

@app.get("/start-excel-call-list")
def start_excel_call_list():
    call_list_path = os.path.join(SCRIPT_DIR, "customers.xlsx")
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
            time.sleep(1)
        print(" Excel Call List Finished ")
        return {"status": "Call list processed", "results": results}
    except Exception as e:
        return {"error": f"Failed to read Excel file: {str(e)}"}

if __name__ == "__main__":
    try:
        import openpyxl
    except ImportError:
        print("WARNING: 'openpyxl' not found. Excel logging will fail. pip install openpyxl")
        time.sleep(2)
    try:
        import dotenv
    except ImportError:
        print("WARNING: 'python-dotenv' not found. Outbound calls will fail. pip install python-dotenv")
        time.sleep(2)

    print(" Starting FastAPI server for Twilio (Hindi voice, runtime translation, product-only) ")
    print(f" Log file: {LOG_FILE} ")
    print(" Server: http://localhost:8000 ")
    print(" Webhook: http://<ngrok>/start-call ")
    uvicorn.run(app, host="0.0.0.0", port=8000)
