"""
Sarvam STT WebSocket bridge for Vapi's custom transcriber integration.

Manages one live connection to Sarvam's streaming STT per call. Vapi sends
raw binary PCM frames (stereo, 16kHz, linear16) to our custom-transcriber
WebSocket; we extract the customer channel, forward it to Sarvam as
base64-wrapped JSON, and relay transcript results back.
"""
import asyncio
import base64
import json
import websockets


class SarvamSTTSession:
    """
    One instance per active call. Opens a Sarvam WebSocket on connect(),
    accepts PCM chunks via send_audio(), and calls on_transcript(text, is_final)
    whenever Sarvam returns a result.
    """

    def __init__(self, api_key: str, language: str, on_transcript):
        self.api_key = api_key
        self.language = language
        self.on_transcript = on_transcript  # callback: (text: str, is_final: bool) -> None
        self._ws = None
        self._receiver_task = None
        self._closed = False

    async def connect(self):
        url = (
            "wss://api.sarvam.ai/speech-to-text/ws"
            f"?language-code={self.language}"
            "&model=saaras:v3"
            "&sample_rate=16000"
            "&input_audio_codec=pcm_s16le"
        )
        self._ws = await websockets.connect(
            url,
            additional_headers={"Api-Subscription-Key": self.api_key},
        )
        self._receiver_task = asyncio.create_task(self._receive_loop())
        print(f"[sarvam_stt] Connected (language={self.language})")

    async def _receive_loop(self):
        try:
            async for raw_msg in self._ws:
                try:
                    msg = json.loads(raw_msg)
                except json.JSONDecodeError:
                    print(f"[sarvam_stt] Non-JSON message ignored: {raw_msg[:100]}")
                    continue

                if msg.get("type") == "data":
                    data = msg.get("data", {})
                    transcript = data.get("transcript", "")
                    if transcript:
                        # Sarvam's streaming API in this mode reports finalized
                        # transcript chunks via "data" events; treat as final.
                        await self._safe_callback(transcript, True)
                else:
                    print(f"[sarvam_stt] Unhandled message type: {msg.get('type')}")
        except websockets.exceptions.ConnectionClosed as exc:
            print(f"[sarvam_stt] Connection closed: {exc}")
        except Exception as exc:
            print(f"[sarvam_stt] Receiver loop error: {exc}")

    async def _safe_callback(self, text: str, is_final: bool):
        try:
            await self.on_transcript(text, is_final)
        except Exception as exc:
            print(f"[sarvam_stt] on_transcript callback error: {exc}")

    async def send_audio(self, pcm_bytes: bytes):
        if self._ws is None or self._closed:
            return
        b64_audio = base64.b64encode(pcm_bytes).decode("ascii")
        payload = {
            "audio": {
                "data": b64_audio,
                "sample_rate": "16000",
                "encoding": "audio/wav",  # per Sarvam's WS message schema
            }
        }
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as exc:
            print(f"[sarvam_stt] send_audio error: {exc}")

    async def close(self):
        self._closed = True
        if self._receiver_task:
            self._receiver_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        print("[sarvam_stt] Session closed")


def extract_customer_channel(stereo_pcm: bytes) -> bytes:
    """
    De-interleaves stereo 16-bit PCM (channel 0 = customer, channel 1 = assistant)
    and returns mono PCM containing only the customer's audio.
    Sarvam's STT expects mono input.
    """
    # Each frame = 4 bytes: 2 bytes (channel 0 sample) + 2 bytes (channel 1 sample)
    if len(stereo_pcm) % 4 != 0:
        # Trim to valid length, per Vapi's own documented buffering approach
        stereo_pcm = stereo_pcm[: len(stereo_pcm) - (len(stereo_pcm) % 4)]

    mono = bytearray()
    for i in range(0, len(stereo_pcm), 4):
        mono += stereo_pcm[i : i + 2]  # channel 0 only (customer)
    return bytes(mono)
