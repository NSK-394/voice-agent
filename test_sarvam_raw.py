"""
Test Sarvam raw PCM output at a specific sample rate — verifies the format
Vapi's custom TTS endpoint will actually need, before wiring anything into FastAPI.
"""
from dotenv import load_dotenv
import os, base64, json

load_dotenv('/root/voice-agent/.env')

from sarvamai import SarvamAI

API_KEY = os.environ.get("SARVAM_API_KEY", "")
client = SarvamAI(api_subscription_key=API_KEY)

TEST_RATE = 24000  # matches Vapi's default sampleRate

response = client.text_to_speech.convert(
    text="Hi, this is a test of raw audio output.",
    target_language_code="hi-IN",
    model="bulbul:v3",
    speaker="priya",
    speech_sample_rate=TEST_RATE,
)

# Inspect the raw response object structure first
print("Response type:", type(response))
print("Response attrs:", [a for a in dir(response) if not a.startswith('_')])

# Try to get the raw audio bytes
audios = response.audios
print("Number of audio clips:", len(audios))

raw_b64 = audios[0]
audio_bytes = base64.b64decode(raw_b64)
print("Decoded byte length:", len(audio_bytes))

# Check if it starts with a WAV header ('RIFF') or is truly raw PCM
header = audio_bytes[:4]
print("First 4 bytes:", header)
if header == b'RIFF':
    print("This is a WAV file (has RIFF header) — needs stripping for Vapi.")
else:
    print("No RIFF header detected — might already be raw PCM.")

# Save it raw so we can inspect with a tool if needed
with open("test_raw_output.bin", "wb") as f:
    f.write(audio_bytes)
print("Saved test_raw_output.bin for inspection.")
import struct

# Parse the WAV header to find exactly where the data starts
# Standard WAV header is 44 bytes, but let's verify, not assume
print("\n--- WAV header inspection ---")
print("ChunkID:", audio_bytes[0:4])
print("ChunkSize:", struct.unpack('<I', audio_bytes[4:8])[0])
print("Format:", audio_bytes[8:12])
print("Subchunk1ID:", audio_bytes[12:16])
print("Subchunk1Size:", struct.unpack('<I', audio_bytes[16:20])[0])
print("AudioFormat:", struct.unpack('<H', audio_bytes[20:22])[0])
print("NumChannels:", struct.unpack('<H', audio_bytes[22:24])[0])
print("SampleRate:", struct.unpack('<I', audio_bytes[24:28])[0])
print("ByteRate:", struct.unpack('<I', audio_bytes[28:32])[0])
print("BlockAlign:", struct.unpack('<H', audio_bytes[32:34])[0])
print("BitsPerSample:", struct.unpack('<H', audio_bytes[34:36])[0])
print("Subchunk2ID (should be 'data'):", audio_bytes[36:40])
print("Subchunk2Size (actual PCM data length):", struct.unpack('<I', audio_bytes[36:40])[0] if audio_bytes[36:40] != b'data' else struct.unpack('<I', audio_bytes[40:44])[0])

# The actual raw PCM data starts right after the 'data' chunk header (byte 44 in standard WAV)
data_chunk_index = audio_bytes.find(b'data')
print("\n'data' chunk found at byte offset:", data_chunk_index)
pcm_start = data_chunk_index + 8  # 'data' (4 bytes) + size field (4 bytes)
pcm_data = audio_bytes[pcm_start:]
print("Raw PCM data length (after stripping header):", len(pcm_data))
print("Expected SampleRate from header should match our requested 24000:", struct.unpack('<I', audio_bytes[24:28])[0])
