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

# ------------------------------
# NLP & Spacy
# ------------------------------
nlp = spacy.load("en_core_web_sm")

# ------------------------------
# Ollama text generation
# ------------------------------
def ai_response(prompt, model_name="phi3:mini"):
    """
    Generate AI response using Ollama local API.
    """
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": model_name, "prompt": prompt}
        )
        return response.json()["response"].strip()
    except Exception as e:
        print("Ollama Error:", e)
        return "I'm sorry, I didn’t catch that."

# ------------------------------
# TTS (edge-tts + pygame)
# ------------------------------
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

def speak(text, voice="en-US-JennyNeural"):
    asyncio.run(speak_async(text, voice=voice))

# ------------------------------
# Speech recognition setup
# ------------------------------
recognizer = sr.Recognizer()
recognizer.energy_threshold = 250
recognizer.dynamic_energy_threshold = True

def listen(source, lang="en-IN"):
    print("Listening...")
    try:
        audio = recognizer.listen(source, timeout=5, phrase_time_limit=8)
        text = recognizer.recognize_google(audio, language=lang)
        print("User:", text)
        return text
    except Exception:
        return "No response"

# ------------------------------
# Emotion detection
# ------------------------------
def detect_emotion(text):
    blob = TextBlob(text)
    s = blob.sentiment.polarity
    if s > 0.3:
        return "happy"
    elif s < -0.3:
        return "angry"
    return "neutral"

# ------------------------------
# Load products from Excel
# ------------------------------
def load_products():
    df = pd.read_excel("products.xlsx")
    df.columns = [c.strip().replace(" ", "_").lower() for c in df.columns]
    required_cols = ["product_name", "description", "price", "product_link"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f" Missing required column in Excel: '{col}'")
    products = df.to_dict(orient="records")
    print(f"Loaded {len(products)} products successfully.")
    return products

# ------------------------------
# Greeting message
# ------------------------------
def intro_message():
    return (
        "Hi there! I’m your sales agent from Creer Infotech. "
        "I’ve reached out to share some exciting offers on our latest products. "
        "Can I take a few minutes to tell you about them?"
    )

# ------------------------------
# Keywords
# ------------------------------
AFFIRMATIVE = ["yes", "ya", "yup", "sure", "ha", "haan", "okay", "ok", "of course", "why not", "alright"]
CALL_KEYWORDS = ["call me", "someone call", "talk to agent", "contact me"]

# ------------------------------
# Main conversation
# ------------------------------
def start_sales_conversation():
    products = load_products()
    df_log = pd.DataFrame(columns=["Question", "User_Response", "Emotion", "AI_Reply", "Timestamp"])

    speak(intro_message())
    time.sleep(1.2)

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=2)
        current_context = intro_message()
        product_explained = False

        while True:
            user_input = listen(source)
            if user_input.lower() in ["exit", "quit", "stop","bye","by","cut","okay bye","ok bye"]:
                speak("Thank you for your time! Have a great day.")
                break

            emotion = detect_emotion(user_input)

            # Step 0: Call request funnel
            if any(word in user_input.lower() for word in CALL_KEYWORDS):
                reply = "Sure! Our agent will call you shortly. Thank you for your time."
                speak(reply)
                ai_reply = reply
                df_log.loc[len(df_log)] = [
                    current_context, user_input, emotion, ai_reply,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
                break

            # Step 1: if user agrees to hear about products
            if any(word in user_input.lower() for word in AFFIRMATIVE) and not product_explained:
                product_text = "Here are our latest offers:\n"
                for p in products:
                    product_text += f"- {p['product_name']}: {p['description']} at ₹{p['price']}\n"
                speak(product_text)
                product_explained = True
                continue

            # Step 2: if user mentions a product
            selected_product = None
            for p in products:
                if p['product_name'].lower() in user_input.lower():
                    selected_product = p
                    break

            if selected_product:
                reply = (
                    f"Great choice! I’ve sent the link of {selected_product['product_name']} "
                    f"to your phone number ending with 0234. "
                    "Thank you for your time! I really appreciate it. "
                    "If you need anything, feel free to contact us."
                    "Our Contact number is 20251."
                )
                speak(reply)
                ai_reply = reply
                df_log.loc[len(df_log)] = [
                    current_context, user_input, emotion, ai_reply,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
                break
            else:
                # Step 3: Normal conversation / persuasion
                prompt = (
                    f"You are a friendly sales agent.\n"
                    f"Products: {products}\n"
                    f"User said: {user_input}\n"
                    f"User emotion: {emotion}\n"
                    f"Respond naturally and briefly."
                )
                ai_reply = ai_response(prompt)
                speak(ai_reply)

            # Log every exchange
            df_log.loc[len(df_log)] = [
                current_context, user_input, emotion, ai_reply,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            current_context = ai_reply

    # Save conversation logs
    file_path = "Sales_Conversation.xlsx"
    if os.path.exists(file_path):
        old = pd.read_excel(file_path)
        df_log = pd.concat([old, df_log], ignore_index=True)
    df_log.to_excel(file_path, index=False)
    print("All your responses have been saved successfully.")

# ------------------------------
# Run the bot
# ------------------------------
if __name__ == "__main__":
    start_sales_conversation()
