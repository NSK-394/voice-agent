"""
Standalone Sarvam STT test — confirms transcription works correctly
before attempting WebSocket streaming integration with Vapi.
"""
from dotenv import load_dotenv
import os

load_dotenv('/root/voice-agent/.env')

from sarvamai import SarvamAI

API_KEY = os.environ.get("SARVAM_API_KEY", "")
client = SarvamAI(api_subscription_key=API_KEY)

# Use the original WAV file from our TTS test (has proper header, not the stripped raw one)
with open("sarvam_hi.wav", "rb") as f:
    response = client.speech_to_text.transcribe(
        file=f,
        language_code="hi-IN",
        model="saaras:v3",
    )

print("Transcript:", response.transcript)
