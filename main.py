import json
import hashlib
import hmac
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

import call_state
import leads as leads_module
import vapi_handlers
from models import VapiWebhookPayload, LeadIn, ClientIn

app = FastAPI(title="Voice AI Agent", docs_url="/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _verify_vapi_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook/vapi")
async def webhook_vapi(request: Request) -> dict:
    from config import get_settings
    settings = get_settings()

    body = await request.body()

    # Verify Vapi signature if a webhook secret is configured
    if settings.VAPI_WEBHOOK_SECRET:
        sig = request.headers.get("x-vapi-signature", "")
        if not sig or not _verify_vapi_signature(body, sig, settings.VAPI_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = VapiWebhookPayload.model_validate_json(body)
    result = await vapi_handlers.route_event(payload.message)
    return {"ok": True, "detail": result}


@app.post("/trigger-retry")
async def trigger_retry() -> dict:
    from config import get_settings
    settings = get_settings()
    pending = call_state.get_pending_retries()
    triggered = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        for call in pending:
            success = await _fire_vapi_call(client, call, settings)
            if success:
                call_state.mark_dialing(call["id"])
                triggered += 1
    return {"triggered": triggered, "total_pending": len(pending)}


async def _fire_vapi_call(client: httpx.AsyncClient, call: dict, settings) -> bool:
    client_id = call.get("client_id", "nikhil_test")
    db_client = call_state.get_client(client_id)
    phone_number_id = (
        db_client["vapi_phone_number_id"]
        if db_client and db_client.get("vapi_phone_number_id")
        else settings.VAPI_PHONE_NUMBER_ID
    )
    try:
        resp = await client.post(
            "https://api.vapi.ai/call/phone",
            headers={
                "Authorization": f"Bearer {settings.VAPI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "phoneNumberId": phone_number_id,
                "assistantId": settings.VAPI_ASSISTANT_ID,
                "customer": {"number": call["phone"]},
                "metadata": {
                    "lead_id": call["lead_id"],
                    "db_call_id": str(call["id"]),
                    "client_id": client_id,
                },
            },
        )
        resp.raise_for_status()
        print(f"[retry] Fired Vapi call for lead {call['lead_id']} (db_id={call['id']}, client={client_id})")
        return True
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300] if exc.response else ""
        print(f"[retry] Vapi call failed for db_id={call['id']}: {exc} | body: {body}")
        return False


@app.get("/leads")
async def get_leads() -> list[dict]:
    return leads_module.list_leads()


@app.post("/leads")
async def add_lead(lead: LeadIn) -> dict:
    return leads_module.ingest_lead(lead)
from fastapi import Response
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/custom-transcriber")
async def custom_transcriber(websocket: WebSocket):
    await websocket.accept()
    import sarvam_stt
    from config import get_settings
    settings = get_settings()

    # Vapi's custom-transcriber handshake carries no call/metadata context,
    # so client_id must come from the WebSocket URL's query string instead
    # (set via assistantOverrides.transcriber.server.url with ?client_id=...)
    client_id = websocket.query_params.get("client_id", "nikhil_test")
    client = call_state.get_client(client_id)
    language = client["language"] if client else "en-IN"

    print(f"[custom-transcriber] WebSocket connected: client={client_id} language={language}")

    session = None

    if language == "en-IN":
        await websocket.close()
        return

    async def on_transcript(text: str, is_final: bool):
        response = {
            "type": "transcriber-response",
            "transcription": text,
            "channel": "customer",
            "transcriptType": "final" if is_final else "partial",
        }
        try:
            await websocket.send_text(json.dumps(response))
        except Exception as exc:
            print(f"[custom-transcriber] Failed to send response to Vapi: {exc}")

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # First message is JSON "start" handshake (not binary)
            if "text" in message and message["text"] is not None:
                try:
                    start_msg = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                if start_msg.get("type") == "start":
                    print(f"[custom-transcriber] start handshake received: {start_msg}")
                    session = sarvam_stt.SarvamSTTSession(
                        api_key=settings.SARVAM_API_KEY,
                        language=language,
                        on_transcript=on_transcript,
                    )
                    await session.connect()
                    return 
                    session = sarvam_stt.SarvamSTTSession(
                        api_key=settings.SARVAM_API_KEY,
                        language=language,
                        on_transcript=on_transcript,
                    )
                    await session.connect()

            # Binary frames are raw stereo PCM audio
            elif "bytes" in message and message["bytes"] is not None:
                if session is None:
                    continue  # haven't received start handshake yet
                stereo_pcm = message["bytes"]
                mono_pcm = sarvam_stt.extract_customer_channel(stereo_pcm)
                await session.send_audio(mono_pcm)

    except WebSocketDisconnect:
        print(f"[custom-transcriber] Vapi disconnected (client={client_id})")
    except Exception as exc:
        print(f"[custom-transcriber] Unexpected error: {exc}")
    finally:
        if session is not None:
            await session.close()
@app.post("/custom-tts")
async def custom_tts(request: Request):
    body = await request.json()
    message = body.get("message", {})

    text = message.get("text", "")
    sample_rate = message.get("sampleRate", 24000)
    call_info = message.get("call", {})
    call_id = call_info.get("id", "")

    # Extract client_id the same way our webhook handler does —
    # check direct metadata first, fall back to assistantOverrides
    metadata = call_info.get("metadata", {}) or {}
    client_id = metadata.get("client_id")
    if not client_id:
        overrides = call_info.get("assistantOverrides", {}) or {}
        client_id = (overrides.get("metadata") or {}).get("client_id", "nikhil_test")

    client = call_state.get_client(client_id)
    language = client["language"] if client else "en-IN"

    print(f"[custom-tts] call={call_id} client={client_id} language={language} "
          f"sample_rate={sample_rate} text_len={len(text)}")

    if language == "en-IN":
        # English stays on Vapi's default pipeline — signal Vapi to fall back
        return Response(status_code=400, content=b"english_uses_default_voice")

    try:
        import sarvam_tts
        pcm_bytes = sarvam_tts.synthesize_raw_pcm(text, language, sample_rate)
    except Exception as exc:
        print(f"[custom-tts] FAILED for call={call_id}: {exc}")
        return Response(status_code=500, content=str(exc).encode())

    return Response(content=pcm_bytes, media_type="application/octet-stream")

@app.post("/fire-pending")
async def fire_pending() -> dict:
    from config import get_settings
    settings = get_settings()
    pending = call_state.get_pending_initial()
    triggered = 0
    async with httpx.AsyncClient(timeout=15.0) as client:
        for call in pending:
            success = await _fire_vapi_call(client, call, settings)
            if success:
                call_state.mark_dialing(call["id"])
                triggered += 1
    return {"triggered": triggered, "total_pending": len(pending)}


@app.get("/clients")
async def get_clients() -> list[dict]:
    return call_state.list_clients()


@app.post("/clients")
async def create_client(body: ClientIn) -> dict:
    call_state.create_client(
        client_id=body.client_id,
        business_name=body.business_name,
        language=body.language,
        system_prompt=body.system_prompt,
        lead_destination_type=body.lead_destination_type,
        lead_destination_value=body.lead_destination_value,
        direction=body.direction,
        vapi_phone_number_id=body.vapi_phone_number_id,
    )
    return {"ok": True, "client_id": body.client_id}


if __name__ == "__main__":
    from config import get_settings
    settings = get_settings()
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
