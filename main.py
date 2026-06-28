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
    except httpx.HTTPError as exc:
        print(f"[retry] Vapi call failed for db_id={call['id']}: {exc}")
        return False


@app.get("/leads")
async def get_leads() -> list[dict]:
    return leads_module.list_leads()


@app.post("/leads")
async def add_lead(lead: LeadIn) -> dict:
    return leads_module.ingest_lead(lead)


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
