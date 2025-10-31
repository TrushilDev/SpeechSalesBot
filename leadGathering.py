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
# Greeting message
# ------------------------------
def intro_message():
    return (
        "Hello there! I’m your sales agent from Creer Infotech. "
        "I hope you’re doing well today. "
        "We have some great products and offers available. "
        "Would you be interested in learning more or buying one of our products?"
    )

# ------------------------------
# Keywords
# ------------------------------
AFFIRMATIVE = ["yes", "ya", "yup", "sure", "ha", "haan", "okay", "ok", "of course", "why not", "alright", "yeah", "yes please"]
NEGATIVE = ["no", "not now", "later", "maybe next time", "nah", "nope", "cancel"]

# ------------------------------
# Main conversation
# ------------------------------
def start_sales_conversation():
    df_leads = pd.DataFrame(columns=["Name", "Interest", "Emotion", "Timestamp"])

    speak(intro_message())
    time.sleep(1.5)

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=2)
        current_context = intro_message()
        got_interest = False
        user_name = None

        while True:
            user_input = listen(source)
            user_input_lower = user_input.lower().strip()
            emotion = detect_emotion(user_input)

            # Exit keywords
            if user_input_lower in ["exit", "quit", "stop", "bye", "goodbye", "ok bye"]:
                speak("Thank you for your time! Have a great day.")
                break

            affirmative_match = any(word in user_input_lower for word in AFFIRMATIVE)
            negative_match = any(word in user_input_lower for word in NEGATIVE)

            # Step 1: If user shows interest
            if affirmative_match and not got_interest:
                speak("That’s great! May I know your good name, please?")
                got_interest = True
                continue

            # Step 2: Capture name
            if got_interest and user_name is None and not affirmative_match and not negative_match:
                user_name = user_input
                speak(f"Thank you {user_name}! Our agent will contact you shortly for further assistance.")
                speak("We appreciate your time. Have a wonderful day!")
                speak("If you have any query feel free to contact us on 20215")
                
                # Save lead
                df_leads.loc[len(df_leads)] = [
                    user_name,
                    "Interested",
                    emotion,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ]
                break

            # Keep conversation flowing naturally
            prompt = (
                f"You are a friendly sales agent. User said: '{user_input}'. "
                f"User emotion: {emotion}. Respond naturally and briefly."
            )
            ai_reply = ai_response(prompt)
            speak(ai_reply)
            current_context = ai_reply

    # ------------------------------
    # Save leads to Excel
    # ------------------------------
    file_path = "Sales_Leads.xlsx"
    if os.path.exists(file_path):
        old = pd.read_excel(file_path)
        df_leads = pd.concat([old, df_leads], ignore_index=True)
    df_leads.to_excel(file_path, index=False)
    print("Lead saved successfully to Sales_Leads.xlsx.")

# ------------------------------
# Run the bot
# ------------------------------
if __name__ == "__main__":
    start_sales_conversation()
