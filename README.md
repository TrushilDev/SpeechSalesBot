Sales Assistant AI Chatbot

Welcome to the Sales Assistant AI Chatbot! This intelligent assistant is designed to help conduct a personalized sales conversation using speech recognition, AI-driven responses, and sentiment analysis. Powered by GPT-4, it can listen to user inputs, generate persuasive replies, and log the entire conversation for future reference.

Features

Speech Recognition: Converts user speech into text using Google's Speech API.

AI-Powered Responses: Generates dynamic replies using GPT-4, personalized to the user’s mood and input.

Emotion Detection: Analyzes sentiment in user responses to adjust conversation tone (happy, angry, neutral).

Text-to-Speech (TTS): Uses Microsoft's edge TTS to vocalize the assistant’s responses.

Product Catalog: Automatically pulls data from an Excel file containing product information and uses it in the conversation.

Conversation Logging: Records all interactions in an Excel file to keep track of user responses and sales efforts.

Requirements

This project requires Python 3.8 or higher and the following dependencies:

Install Dependencies
pip install -r requirements.txt

Key Libraries Used:

speech_recognition: For converting speech to text.

pandas: For managing product data and conversation logs.

pygame: For playing text-to-speech audio.

spacy: For sentiment analysis and basic NLP tasks.

edge-tts: To convert text into spoken words.

gpt4all: To generate AI-driven responses using the GPT-4 model.

textblob: For analyzing sentiment polarity in user responses.

Additional Setup:

Install SpaCy model:

python -m spacy download en_core_web_sm

Setup Instructions
Step 1: Prepare the Product Catalog

Ensure that you have a file named products.xlsx in the same directory as your script. The file should contain a list of products in the following format:

Product Name	Price	Description
Product A	$100	A great product for your needs.
Product B	$200	High-quality and durable.

The bot will reference this file during conversations to share product details.

Step 2: Verify Sound Setup

The program uses pygame to play back text-to-speech audio. Make sure your sound system is configured correctly and that your speakers or headphones are connected.

How It Works

The assistant operates in a loop, where it starts by greeting the user and offering to share details about products. It listens to the user's responses, generates AI-driven replies, and adapts the conversation based on detected emotions (e.g., happy, angry, neutral).

Example Flow:

Greeting:
The assistant introduces itself and offers to tell the user about the latest products.

User Response:
The assistant listens for a spoken response, processes it with speech-to-text, and determines the user's sentiment (happy, angry, neutral).

AI Response:
Based on the sentiment and context of the conversation, the assistant generates a response using GPT-4. If the user expresses disinterest, the assistant can offer discounts or additional product information.

Exit:
If the user says “exit”, “quit”, or “stop”, the assistant thanks the user and ends the conversation.

Dynamic AI Behavior:

The assistant adjusts its tone and responses based on sentiment analysis. For example:

If the user is happy, the assistant will maintain an upbeat and positive tone.

If the user seems angry, the assistant will try to de-escalate and offer discounts or a more empathetic approach.

Running the Program

To run the assistant, follow these steps:

Clone or download this repository to your local machine.

Install all necessary dependencies with pip install -r requirements.txt.

Prepare the products.xlsx file with product details.

Execute the script:

python speech.py


The assistant will greet you, offer product details, and listen for your responses.

Example Interaction
AI:

"Hi there! I’m your sales agent from Creer Infotech. I’ve reached out to share some exciting offers on our latest products. Can I take a few minutes to tell you about them?"

User:

"Sure, tell me about the products."

AI:

"We have some amazing products! For example, we have Product A, which is great for those looking for something budget-friendly. Would you like to learn more?"

User:

"No, not really."

AI:

"I understand! What if I told you there's a 10% discount on Product A for a limited time? Would that change your mind?"

Conversation Logging

Every interaction is logged into an Excel file (Sales_Conversation.xlsx). The log includes:

Question: The assistant's query or prompt.

User Response: What the user said.

Emotion: The sentiment detected in the user's response (happy, angry, neutral).

AI Response: The assistant's reply.

Timestamp: When the conversation took place.

Example log format:

Question	User Response	Emotion	AI Response	Timestamp
"Greeting"	"Sure, tell me about the products."	Neutral	"Here are the products..."	2025-10-30 14:12:03
"Product Info"	"No, not really."	Neutral	"What if I gave you a 10% discount?"	2025-10-30 14:14:56
Troubleshooting

No Sound? Ensure your system's sound is configured properly, and pygame is installed.

Microphone Issues? Check if your microphone is connected and recognized by the system. You can adjust the microphone settings in your system’s audio settings.

Installation Errors? Double-check your Python version and dependencies. Ensure you’ve installed all required libraries with pip install -r requirements.txt.

Conclusion

This AI-powered Sales Assistant is designed to engage users in personalized, dynamic conversations, offering product information and persuasive sales tactics based on real-time feedback and sentiment. By logging every conversation, you can review user responses and adjust strategies for better outcomes.

Feel free to customize the products.xlsx file with your product catalog and tweak any configurations as needed.