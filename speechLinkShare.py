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
from difflib import SequenceMatcher

# ------------------------------
# NLP & Spacy
# ------------------------------
nlp = spacy.load("en_core_web_sm")

# ------------------------------
# Ollama text generation
# ------------------------------
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

# ------------------------------
# TTS (edge-tts + pygame)
# ------------------------------
async def speak_async(text, voice="en-US-JennyNeural", rate="-15%"):
    try:
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            await communicate.save(f.name)
            temp_path = f.name

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.05)
        pygame.mixer.music.stop()

        for _ in range(5):
            try:
                os.remove(temp_path)
                break
            except PermissionError:
                time.sleep(0.2)
    except Exception as e:
        print("TTS Error:", e)

def speak(text, voice="en-US-JennyNeural"):
    asyncio.run(speak_async(text, voice=voice))

# ------------------------------
# Speech recognition
# ------------------------------
recognizer = sr.Recognizer()
recognizer.energy_threshold = 200
recognizer.dynamic_energy_threshold = False

def listen(source, lang="en-IN"):
    print("Listening...")
    try:
        audio = recognizer.listen(source, timeout=3, phrase_time_limit=5)
        text = recognizer.recognize_google(audio, language=lang)
        print("User:", text)
        return text
    except sr.WaitTimeoutError:
        return "No response"
    except sr.UnknownValueError:
        speak("Could not understand")
        return "No response"
    except Exception as e:
        print("Recognition Error:", e)
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
# Load products
# ------------------------------
def load_products():
    df = pd.read_excel("products.xlsx")
    df.columns = [c.strip().replace(" ", "_").lower() for c in df.columns]
    required_cols = ["product_name", "description", "price", "product_link"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column in Excel: '{col}'")
    products = df.to_dict(orient="records")
    print(f"Loaded {len(products)} products successfully.")
    return products

# ------------------------------
# Greeting
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
NEGATIVE = ["no", "nope", "not now", "not interested", "maybe later", "no thanks"]
CALL_KEYWORDS = ["call me", "talk to agent", "contact me", "speak to agent", "connect me to agent"]

# ------------------------------
# SMS via Tripada
# ------------------------------
def send_sms_via_tripada(mobile_number, message):
    try:
        params = {
            "auth_key": "3H",
            "mobiles": str(mobile_number),
            "message": message,
            "sender": "AUAGPT",
            "route": "4",
            "templateid": "1207167663997777761"
        }
        response = requests.get("https://sms.shreetripada.com/api/sendapi.php", params=params)
        print("Tripada SMS Response:", response.text)
    except Exception as e:
        print("Failed to send SMS via Tripada:", e)

# ------------------------------
# Main conversation
# ------------------------------
def start_sales_conversation():
    products = load_products()
    df_log = pd.DataFrame(columns=["Question", "User_Response", "Emotion", "AI_Reply", "Timestamp"])

    speak(intro_message())
    time.sleep(0.6)

    with sr.Microphone() as source:
        recognizer.adjust_for_ambient_noise(source, duration=1)
        current_context = intro_message()
        product_explained = False
        persuasion_used = 0  

        offers = [
            "I completely understand! But before you go — we’re giving a 20% discount just for today. Would you like to take a quick look?",
            "Totally fair! But if I may — we’re offering free delivery on all products this week. Can I share a few top deals?",
            "I hear you! However, we’ve got a limited-time combo offer where you can save even more. Would you like to check that out?",
            "Alright! But trust me, this week’s festive sale is really something special — 25% off on bestsellers! Interested?",
            "Okay, I get it. Still, let me tell you — even browsing our collection could give you an idea for your next purchase. Shall I share a link?",
            "No problem at all! But just one last thing — we’re giving exclusive coupons for early customers today. Should I send one to you?"
        ]

        while True:
            user_input = listen(source)
            user_input_lower = user_input.lower().strip()
            emotion = detect_emotion(user_input)

            # --- Exit ---
            if user_input_lower in ["exit", "quit", "stop", "bye", "ok bye", "goodbye"]:
                speak("Thank you for your time! Have a great day.")
                break

            # --- Handle NO with persuasion ---
            if any(word in user_input_lower for word in NEGATIVE):
                persuasion_used += 1
                if persuasion_used <= len(offers):
                    speak(offers[persuasion_used - 1])
                    continue
                else:
                    speak("No worries! Have a great day ahead.")
                    break

            # --- Handle YES (start product listing) ---
            if any(word in user_input_lower for word in AFFIRMATIVE) and not product_explained:
                product_explained = True
                product_text = "Here are our latest offers:\n"
                for p in products:
                    product_text += f"- {p['product_name']}\n"
                speak(product_text)
                speak("Which product would you like to purchase?")
                continue

            # --- Handle CALL agent ---
            if any(kw in user_input_lower for kw in CALL_KEYWORDS):
                current_hour = datetime.now().hour
                if 11 <= current_hour < 17:
                    speak("Please wait until the agent is connected...")
                    time.sleep(3)
                    speak("You are now connected to the agent. Ending the conversation. Thank you!")
                    break
                else:
                    speak("Our agent will contact you later.")
                    speak("Meanwhile, would you like to hear about our products?")
                    continue

            # --- Handle Info request ---
            INFO_KEYWORDS = ["tell me more", "details", "more info", "specs", "specifications", "explain", "description", "features"]
            if any(kw in user_input_lower for kw in INFO_KEYWORDS):
                found_product = None
                for p in products:
                    if p["product_name"].lower() in user_input_lower:
                        found_product = p
                        break
                if found_product:
                    info_reply = (
                        f"{found_product['product_name']} — {found_product['description']}. "
                        f"The price is ₹{found_product['price']}. "
                        f"You can check it out here: {found_product['product_link']}. "
                        "Would you like to purchase it?"
                    )
                    speak(info_reply)
                    continue
                else:
                    speak("Could you please specify which product you want more details about?")
                    continue

            # --- Match Product Name ---
            def similar(a, b): return SequenceMatcher(None, a, b).ratio()
            selected_product = None
            for p in products:
                name = p["product_name"].lower()
                if similar(name, user_input_lower) > 0.6 or any(word in user_input_lower for word in name.split()):
                    selected_product = p
                    break

            if selected_product:
                mobile_number = "7990747606"
                product_link = selected_product["product_link"]
                message = (
                    f"Dear customer, here is the link for {selected_product['product_name']}: "
                    f"{product_link}\nAUAG METALLIC LLP"
                )
                send_sms_via_tripada(mobile_number, message)
                last_digits = "".join(mobile_number[-4:])
                speak(
                    f"Great choice! I’ve sent the link of {selected_product['product_name']} "
                    f"to your phone number ending with {last_digits}. "
                    "Thank you for your time! I really appreciate it."
                )
                break
            else:
                speak("Sorry, we don’t have that product right now.")
                product_text = "Here are our latest offers:\n"
                for p in products:
                    product_text += f"- {p['product_name']}: {p['description']} at ₹{p['price']}\n"
                speak(product_text)
                speak("Which product would you like to purchase?")
                continue

    # --- Save logs ---
    file_path = "Sales_Conversation.xlsx"
    if os.path.exists(file_path):
        old = pd.read_excel(file_path)
        df_log = pd.concat([old, df_log], ignore_index=True)
    df_log.to_excel(file_path, index=False)
    print("All your responses have been saved successfully.")


# ------------------------------
# Run
# ------------------------------
if __name__ == "__main__":
    start_sales_conversation()
