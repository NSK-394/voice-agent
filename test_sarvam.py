"""
Standalone Sarvam TTS test — Phase 2, step 1.
Generates 4 .wav files (Hindi, Tamil, Telugu, Kannada) using sample
qualification-call phrases. Does NOT touch Vapi or any phone call.

Run: python test_sarvam.py
"""
from dotenv import load_dotenv
import os

load_dotenv('/root/voice-agent/.env')

from sarvamai import SarvamAI
from sarvamai.play import save

API_KEY = os.environ.get("SARVAM_API_KEY", "")
if not API_KEY:
    raise RuntimeError("SARVAM_API_KEY not found in .env")

client = SarvamAI(api_subscription_key=API_KEY)

SAMPLES = {
    "hi-IN": "नमस्ते, मैं एलेक्स बात कर रहा हूं। क्या आपको हमारी सेवा में रुचि है?",
    "ta-IN": "வணக்கம், நான் அலெக்ஸ் பேசுகிறேன். உங்களுக்கு எங்கள் சேவையில் ஆர்வம் உள்ளதா?",
    "te-IN": "నమస్కారం, నేను అలెక్స్ మాట్లాడుతున్నాను. మీకు మా సేవపై ఆసక్తి ఉందా?",
    "kn-IN": "ನಮಸ್ಕಾರ, ನಾನು ಅಲೆಕ್ಸ್ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ. ನಿಮಗೆ ನಮ್ಮ ಸೇವೆಯಲ್ಲಿ ಆಸಕ್ತಿ ಇದೆಯೇ?",
}

for lang_code, text in SAMPLES.items():
    print(f"Generating {lang_code}...")
    try:
        response = client.text_to_speech.convert(
            text=text,
            target_language_code=lang_code,
            model="bulbul:v3",
            speaker="priya",
        )
        filename = f"sarvam_{lang_code.split('-')[0]}.wav"
        save(response, filename)
        print(f"  Saved: {filename}")
    except Exception as exc:
        print(f"  FAILED for {lang_code}: {exc}")

print("\nDone. Download the .wav files and listen before proceeding.")
