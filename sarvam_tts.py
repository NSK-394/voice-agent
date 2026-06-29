"""
Sarvam TTS wrapper for Vapi's custom-voice integration.
Strips the WAV header Sarvam always returns, leaving raw PCM
exactly as Vapi's custom TTS spec requires.
"""
from sarvamai import SarvamAI
import base64

_LANGUAGE_SPEAKER_MAP = {
    "hi-IN": "priya",
    "ta-IN": "priya",
    "te-IN": "priya",
    "kn-IN": "priya",
    "en-IN": "priya",
}

_WAV_HEADER_SIZE = 44  # confirmed via test_sarvam_raw.py — standard WAV, no extra chunks


def synthesize_raw_pcm(text: str, language: str, sample_rate: int) -> bytes:
    """
    Calls Sarvam TTS and returns raw PCM bytes (WAV header stripped),
    ready to send directly to Vapi's custom-tts response.
    """
    from config import get_settings
    settings = get_settings()

    client = SarvamAI(api_subscription_key=settings.SARVAM_API_KEY)
    speaker = _LANGUAGE_SPEAKER_MAP.get(language, "priya")

    response = client.text_to_speech.convert(
        text=text,
        target_language_code=language,
        model="bulbul:v3",
        speaker=speaker,
        speech_sample_rate=sample_rate,
    )

    audio_bytes = base64.b64decode(response.audios[0])

    if audio_bytes[:4] != b"RIFF":
        # Defensive check — if Sarvam ever changes behavior, fail loudly
        # instead of silently sending malformed audio to Vapi
        raise ValueError(f"Expected WAV (RIFF) header, got: {audio_bytes[:4]!r}")

    return audio_bytes[_WAV_HEADER_SIZE:]
