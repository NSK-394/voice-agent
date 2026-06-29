"""
Standalone test of SarvamSTTSession — streams real PCM audio (de-interleaved
from our existing test files) into a live Sarvam WebSocket and checks if we
get transcripts back, before wiring into the Vapi-facing endpoint.
"""
import asyncio
from dotenv import load_dotenv
import os

load_dotenv('/root/voice-agent/.env')

from sarvam_stt import SarvamSTTSession

API_KEY = os.environ.get("SARVAM_API_KEY", "")

received_transcripts = []

async def on_transcript(text, is_final):
    print(f"[TEST] Got transcript (final={is_final}): {text}")
    received_transcripts.append(text)

async def main():
    session = SarvamSTTSession(api_key=API_KEY, language="hi-IN", on_transcript=on_transcript)
    await session.connect()

    # Use the raw stripped PCM we already generated and verified earlier
    with open("test_raw_hindi_correct.bin", "rb") as f:
        pcm_data = f.read()

    print(f"Streaming {len(pcm_data)} bytes of mono PCM to Sarvam...")

    # Send in chunks to simulate real streaming (not all at once)
    chunk_size = 4096
    for i in range(0, len(pcm_data), chunk_size):
        chunk = pcm_data[i:i + chunk_size]
        await session.send_audio(chunk)
        await asyncio.sleep(0.05)  # small delay between chunks

    print("Done sending. Waiting 5s for final transcripts...")
    await asyncio.sleep(5)

    await session.close()
    print(f"\nTotal transcripts received: {len(received_transcripts)}")
    for t in received_transcripts:
        print(" -", t)

if __name__ == "__main__":
    asyncio.run(main())

