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
import uvicorn
from fastapi import FastAPI, Form, Response, Query, Request, BackgroundTasks, APIRouter
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client
from dotenv import load_dotenv
from urllib.parse import quote
from multi_agent_core import run_multi_agent
from urllib.parse import quote
import os


load_dotenv()


router = APIRouter()
# NLP & Spacy
nlp = spacy.load("en_core_web_sm")

# golab variable 
CONV_STATE = {} 

# Ollama text generation
def ai_response(prompt, model_name="phi3:mini"):
    """Generate AI response using Ollama local API."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "prompt": prompt}
        )
        return response.json()["response"].strip()
    except Exception as e:
        print("Ollama Error:", e)
        return "I'm sorry, I didn’t catch that."
    
    # simple llm 
def simple_llm(prompt):
    """Lightweight LLM for short conversational output."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "phi3:mini", "prompt": prompt},
            timeout=2
        )
        return response.json().get("response", "").strip()
    except:
        return ""
    
    
# Emotion detection
def detect_emotion(text):
    blob = TextBlob(text)
    s = blob.sentiment.polarity
    if s > 0.3:
        return "happy"
    elif s < -0.3:
        return "angry"
    return "neutral"

# Greeting message
def intro_message():
    return (
        "Hello there! I’m your sales agent from Creer Infotech. "
        "I hope you’re doing well today. "
        "We have some great products and offers available. "
        "Would you be interested in learning more or buying one of our products?"
    )

# Keywords
AFFIRMATIVE = ["yes", "ya", "yup", "sure", "ha", "haan", "okay", "ok", "of course", "why not", "alright", "yeah", "yes please"]
NEGATIVE = ["no", "not now", "later", "maybe next time", "nah", "nope", "cancel"]

#  lead loading
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "Sales_Leads.xlsx") 
print(f" ‼ Logging leads to: {LOG_FILE} ‼ ")

# data store in the excel sheet 
def log_lead_excel(user_name, interest, emotion, phone_number):
    new_lead = pd.DataFrame({
        "Name": [user_name],
        "Interest": [interest],
        "Emotion": [emotion],
        "PhoneNumber": [phone_number],
        "Timestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    })
    
    try:
        # Check for openpyxl
        try:
            import openpyxl
        except ImportError:
            print(" ERROR: 'openpyxl' not found. Please 'pip install openpyxl' ")
            return

        if os.path.exists(LOG_FILE):
            old = pd.read_excel(LOG_FILE)
            df_leads = pd.concat([old, new_lead], ignore_index=True)
        else:
            df_leads = new_lead
        
        df_leads.to_excel(LOG_FILE, index=False)
        print(f" Lead saved for {user_name} ")
    
    except Exception as e:
        print(f" CRITICAL ERROR logging lead to Excel: {e} ")
        
        
#  Helper function for TwiML responses with silence retry 
def create_twiml_response(text_to_say: str, action_url: str):
    response = VoiceResponse()
    gather = Gather(
        input="speech", 
        language="en-IN",
        speechModel="phone_call", 
        speechTimeout="auto",
        bargeIn = True, 
        action=action_url, 
        method="POST")
    gather.say(text_to_say)
    response.append(gather)

    # Retry 2 times on silence
    # for _ in range(2):
    #     response.say("I'm sorry, I didn't hear a response. Are you still there?")
    #     retry_gather = Gather(
    #         input="speech",
    #         language="en-IN",
    #         speechTimeout="auto",
    #         bargeIn = True,
    #         enhanced=True,
    #         action=action_url,
            
    #         method="POST"
    #         )
    #     response.append(retry_gather)

    # response.say("We still didn't hear a response. Goodbye.")
    # response.hangup()
    return Response(content=str(response), media_type="application/xml")

#  Helper function to build the next URL with state 
def build_next_url(state: str, phone: str):
    safe_phone = quote(phone)
    return f"/lead/handle-conversation?state={state}&phone={safe_phone}"

#  This endpoint starts the call captures user's number 
# @app.post("/start-call")
@router.post("/start-call")
@router.get("/start-call")
def start_call(request: Request, From: str = Form(None), To: str = Form(None)):
    """ This is the first endpoint Twilio calls. Catches the 'To' number. """
    print(f" New Call Started. From: {From}, To: {To} ")
    
    # Use 'To' the user's number for the state
    user_phone = To if To else "Unknown"
    
    # The first state is "awaiting_interest"
    action_url = build_next_url("awaiting_interest", user_phone)
    intro = intro_message()
    
    # We don't log a lead yet, just start the conversation
    return create_twiml_response(intro, action_url)

#  This endpoint handles the entire conversation loop 
# @app.post("/handle-conversation")
@router.post("/handle-conversation")
@router.get("/handle-conversation")
def handle_conversation(
    background_tasks: BackgroundTasks, 
    SpeechResult: str = Form(None),
    state: str = Query("awaiting_interest"), 
    phone: str = Query("Unknown"),
    ):
    """
    This is the main "loop" based on your new script's logic.
    """
    response = VoiceResponse()
    
    # initialize retry counter for this phone 
    if phone not in CONV_STATE:
        CONV_STATE[phone] = {"retries":0}
        
    user_input = SpeechResult if SpeechResult else ""
    user_input_lower = user_input.lower().strip()
    emotion = detect_emotion(user_input)
    
    print(f"User ({phone}) said: {user_input} (State: {state})")

    affirmative_match = any(word in user_input_lower for word in AFFIRMATIVE)
    negative_match = any(word in user_input_lower for word in NEGATIVE)

    # If user shows interest 
    if state == "awaiting_interest":
        # if user says yes
        if affirmative_match:
            CONV_STATE[phone]["retries"] = 0
            ai_reply_text = "That’s great! May I know your good name, please?"
            next_action_url = build_next_url("awaiting_name", phone) 
            return create_twiml_response(ai_reply_text, next_action_url)
        
        # elif negative_match or user_input_lower in ["exit", "quit", "stop", "bye", "goodbye", "ok bye"]:
        #     ai_reply_text = "No problem. Thank you for your time! Have a great day."
        #     response.say(ai_reply_text)
        #     response.hangup()
        #     return Response(content=str(response), media_type="application/xml")
        
        # if users says no 
        if negative_match:
            CONV_STATE[phone]["retries"] += 1
            retry_count = CONV_STATE[phone]["retries"]

            print(f"Persuasion attempt #{retry_count} for {phone}")

            if retry_count >= 5:
                response.say("No problem.Thank you for your time! Have a great day.")
                response.hangup()
                return Response(content=str(response), media_type="application/xml")

            PERSUASIVE_LINES = [
                "Sir, just 10 seconds please, I promise this is helpful.",
                "Sir, this will really benefit you, just hear me out for a moment.",
                "Sir, one quick thing — this offer is really worthwhile.",
                "Sir, just a moment, I believe this can help you a lot.",
                "Sir, trust me, this information may be important for you."
            ]

            persuasive_reply = PERSUASIVE_LINES[(retry_count - 1) % len(PERSUASIVE_LINES)]
            persuasive_reply = simple_llm(persuasive_reply)

            if not persuasive_reply or len(persuasive_reply.strip()) < 2:
                persuasive_reply = "Sir, just give me 10 seconds, this is really beneficial for you."

            next_action_url = build_next_url("awaiting_interest", phone)
            return create_twiml_response(persuasive_reply, next_action_url)
        
        # unclear ask again using ai 
        fallback_prompt = (
            f"You are a friendly sales agent. "
            f"User said:'{user_input}'. Emotion: {emotion}. "
            "Ask again politely if they are interested in one short line. " 
        )
        
        fallback_reply = simple_llm(fallback_prompt)
        if not fallback_reply.strip():
            fallback_reply = "Just checking again sir, would like to know about our offers?"
        next_action_url = build_next_url("awaiting_interest", phone)
        return create_twiml_response(fallback_reply,next_action_url)
        
        # # Fallback for this state if not yes/no
        # prompt = f"You are a friendly sales agent. User said: '{user_input}'. User emotion: {emotion}. Your goal is to ask if they are interested. Respond naturally and briefly."
        # ai_reply = ai_response(prompt)
        # next_action_url = build_next_url("awaiting_interest", phone) 
        # return create_twiml_response(ai_reply, next_action_url)

    #  Capture name 
    elif state == "awaiting_name":
        # Check if it's a valid name not just "yes" or "no" or empty
        cleaned = user_input_lower.strip()
        if cleaned not in ["", "no response"] and cleaned not in AFFIRMATIVE and cleaned not in NEGATIVE:
            user_name = SpeechResult 
            
            #  This is your final message 
            ai_reply_text = (
                f"Thank you {user_name}! Our agent will contact you shortly for further assistance. "
                "We appreciate your time. Have a wonderful day! "
                "If you have any query feel free to contact us on 20215"
            )
            
             #  This is your lead-saving logic
            background_tasks.add_task(log_lead_excel, user_name, "Interested", emotion, phone)
            
            # This part now runs instantly
            response.say(ai_reply_text)
            response.hangup()
            return Response(content=str(response), media_type="application/xml")
        
        else:
            # User said something other than a name
            ai_reply_text = "I'm sorry, I didn't quite catch your name. Could you please tell me your name?"
            next_action_url = build_next_url("awaiting_name", phone) 
            return create_twiml_response(ai_reply_text, next_action_url)
            
    #  Default fallback if state is unknown 
    ai_reply_text = "I'm sorry, I seem to have lost my place. Goodbye."
    response.say(ai_reply_text)
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


#  ENDPOINTS TO TRIGGER OUTBOUND CALLS 
def _initiate_call(user_number: str):
    """Helper function to load env vars and make a single call."""
    load_dotenv()

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_number = os.getenv("TWILIO_NUMBER")

    # 🔍 Get raw NGROK_URL and sanitize it
    ngrok_raw = os.getenv("NGROK_URL", "")
    print("RAW NGROK_URL repr ->", repr(ngrok_raw))

    # Strip spaces, quotes, trailing slash
    ngrok_url = ngrok_raw.strip().strip('"').strip("'").rstrip("/")
    print("CLEAN NGROK_URL repr ->", repr(ngrok_url))

    if not all([account_sid, auth_token, twilio_number, ngrok_url]):
        print(" ERROR: Missing .env variables ")
        return {
            "error": "Missing .env variables (SID, TOKEN, TWILIO_NUMBER, NGROK_URL)"
        }

    try:
        # ✅ ALWAYS https, ALWAYS full absolute URL
        start_call_url = f"{ngrok_url}/lead/start-call"
        print("FINAL start_call_url repr ->", repr(start_call_url))

        client = Client(account_sid, auth_token)
        print(f" Attempting to call: {user_number} ")

        # 🔥 TEST 1: Try Twilio demo URL to confirm Twilio client is okay
        # demo_call = client.calls.create(
        #     to=user_number,
        #     from_=twilio_number,
        #     url="https://demo.twilio.com/welcome/voice/"
        # )
        # print("✅ Demo call created:", demo_call.sid)

        # 🔥 REAL CALL with your URL
        call = client.calls.create(
            to=user_number,
            from_=twilio_number,
            url=start_call_url,
        )
        print(f"✅ Successfully initiated call! SID: {call.sid}")
        return {"status": "Call initiated", "sid": call.sid, "to": user_number}
    except Exception as e:
        print(f"❌ Error making call to {user_number}: {repr(e)} ")
        return {"status": "Failed", "error": str(e), "to": user_number}

# @app.get("/start-outbound-call")
# def start_outbound_call(phone: str):
#     """ Triggers a single outbound call. """
#     if not phone:
#         return {"error": "Provide a 'phone' query parameter."}
#     return _initiate_call(phone)

# @app.get("/start-excel-call-list")
# def start_excel_call_list():
#     """ Reads 'call_list.xlsx' and calls every number. """
#     call_list_path = os.path.join(SCRIPT_DIR, "customers.xlsx")
#     if not os.path.exists(call_list_path):
#         return {"error": "call_list.xlsx not found."}

#     try:
#         df = pd.read_excel(call_list_path)
#         if "phone" not in df.columns:
#             return {"error": "Excel file must have a 'phone' column."}
        
#         phone_numbers = df["phone"].dropna().tolist()
#         results = []
#         print(f" Starting Excel Call List ({len(phone_numbers)} numbers) ")
#         for number in phone_numbers:
#             result = _initiate_call(str(number))
#             results.append(result)
#             time.sleep(1) # Delay between calls
        
#         print(" Excel Call List Finished ")
#         return {"status": "Call list processed", "results": results}
#     except Exception as e:
#         return {"error": f"Failed to read Excel file: {str(e)}"}

#  This is how you run the new FastAPI server 
# if __name__ == "__main__":
    # Check for required libraries
    # try:
    #     import openpyxl
    # except ImportError:
    #     print(" WARNING: 'openpyxl' not found. Excel logging will fail. 'pip install openpyxl' ")
    #     time.sleep(3)
    # try:
    #     import dotenv
    # except ImportError:
    #     print(" WARNING: 'python-dotenv' not found. Outbound calls will fail. 'pip install python-dotenv' ")
    #     time.sleep(3)

    # print(" Starting FastAPI server for Twilio (Lead Gen Bot) ")
    # print(f" Log file will be saved at: {LOG_FILE} ")
    # print(" Your server will be at http://localhost:8000 ")
    # print(" Your first Twilio webhook URL will be http://<your_ngrok_url>/start-call ")
    # print("\n Outbound Call Endpoints ")
    # print("Call a single number: http://localhost:8000/start-outbound-call?phone=NUMBER_TO_CALL")
    # print("Call from Excel list: http://localhost:8000/start-excel-call-list")
    
    # uvicorn.run(app, host="0.0.0.0", port=8000)