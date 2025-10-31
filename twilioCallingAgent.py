import os
import time
import speech_recognition as sr
import pandas as pd
from datetime import datetime
import asyncio
import edge_tts
import tempfile
import pygame
import spacy
from textblob import TextBlob
import requests
import string
from twilio.rest import Client
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks

load_dotenv()

# --- FASTAPI APP ---
app = FastAPI(title="AI Sales ", description="Voice-enabled Sales Agent", version="1.0")

# --- NLP + TTS + Models ---
nlp = spacy.load("en_core_web_sm")

# Ollama text generation (fallback)
def ai_response(prompt, model_name="phi3:mini"):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "prompt": prompt}
        )
        return response.json()["response"].strip()
    except Exception as e:
        print("Ollama Error:", e)
        return "I'm sorry, I didn't catch that."


# --- TWILIO CALL FUNCTION ---
def make_call(message):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
    destination_number = os.getenv("DESTINATION_NUMBER")

    if not all([account_sid, auth_token, twilio_number, destination_number]):
        print("❌ Missing Twilio credentials.")
        return

    try:
        client = Client(account_sid, auth_token)
        call = client.calls.create(
            twiml=f'<Response><Say voice="alice">{message}</Say></Response>',
            to=destination_number,
            from_=twilio_number
        )
        print(f"✅ Call initiated to {destination_number}, Call SID: {call.sid}")
    except Exception as e:
        print("❌ Twilio Error:", e)


# --- TEXT TO SPEECH (Local) ---
async def speak_async(text, voice="en-US-JennyNeural", rate="-15%"):
    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            await communicate.save(f.name)
            temp_path = f.name
        pygame.mixer.init()
        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        pygame.mixer.quit()
        os.remove(temp_path)
    except Exception as e:
        print("TTS Error:", e)

def speak(text):
    asyncio.run(speak_async(text))


# --- SPEECH RECOGNITION ---
recognizer = sr.Recognizer()
recognizer.energy_threshold = 250
recognizer.dynamic_energy_threshold = True

def listen(source, lang="en-IN"):
    print("🎤 Listening...")
    try:
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
        text = recognizer.recognize_google(audio, language=lang)
        print("👂 User:", text)
        return text
    except Exception:
        return "No response"


# --- SENTIMENT / EMOTION ---
def detect_emotion(text):
    blob = TextBlob(text)
    s = blob.sentiment.polarity
    if s > 0.3:
        return "happy"
    elif s < -0.3:
        return "angry"
    return "neutral"


# --- LOAD PRODUCTS ---
def load_products():
    df = pd.read_excel("products.xlsx")
    df.columns = [c.strip().replace(" ", "_").lower() for c in df.columns]
    required = ["product_name", "description", "price", "product_link"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing column: {c}")
    return df.to_dict(orient="records")


# --- SALES LOGIC ---
AFFIRMATIVE = ["yes", "ya", "yup", "sure", "ha", "haan", "okay", "ok", "of course", "why not", "alright"]

def is_affirmative(user_input):
    user_input = user_input.lower().translate(str.maketrans('', '', string.punctuation))
    return any(word in AFFIRMATIVE for word in user_input.split())


def start_sales_conversation():
    products = load_products()
    df_log = pd.DataFrame(columns=["Question", "User_Response", "Emotion", "AI_Reply", "Timestamp"])

    greeting = (
        "Hi there! I’m your AI sales agent from Creer Infotech. "
        "I have some exciting offers for you. "
        "Would you like to hear about them?"
    )

    make_call(greeting)
    speak(greeting)

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=2)

        current_context = greeting
        products_explained = False

        while True:
            user_input = listen(source)
            if user_input.lower() in ["exit", "quit", "stop", "bye"]:
                speak("Thank you for your time! Have a great day.")
                break

            emotion = detect_emotion(user_input)

            # Step 1: If user agrees to hear offers
            if is_affirmative(user_input) and not products_explained:
                product_text = "Here are our latest offers:\n"
                for p in products:
                    product_text += f"- {p['product_name']}: {p['description']} at ₹{p['price']}\n"
                speak(product_text)
                products_explained = True
                continue

            # Step 2: If user mentions a product name
            selected_product = None
            for p in products:
                if p['product_name'].lower() in user_input.lower():
                    selected_product = p
                    break

            if selected_product:
                reply = (
                    f"Great choice! I’ve sent the link of {selected_product['product_name']} "
                    f"to your phone number ending with 0234. Thank you for your time!"
                )
                speak(reply)
                df_log.loc[len(df_log)] = [
                    current_context,
                    user_input,
                    emotion,
                    reply,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ]
                break

            # Step 3: Default AI fallback
            prompt = (
                f"You are a friendly sales agent.\n"
                f"Products: {products}\n"
                f"User said: {user_input}\n"
                f"User emotion: {emotion}\n"
                f"Respond naturally and briefly."
            )
            ai_reply = ai_response(prompt)
            speak(ai_reply)

            df_log.loc[len(df_log)] = [
                current_context,
                user_input,
                emotion,
                ai_reply,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ]
            current_context = ai_reply

    # Save conversation
    file_path = "Sales_Conversation.xlsx"
    if os.path.exists(file_path):
        old = pd.read_excel(file_path)
        df_log = pd.concat([old, df_log], ignore_index=True)
    df_log.to_excel(file_path, index=False)
    print("✅ All responses saved successfully.")


# --- FASTAPI ENDPOINTS ---

@app.get("/")
def root():
    return {"status": "AI Sales Agent API running 🚀"}


@app.post("/start-call")
def start_call(background_tasks: BackgroundTasks):
    """Start the voice-based sales conversation asynchronously"""
    background_tasks.add_task(start_sales_conversation)
    return {"message": "Sales conversation started in background."}
