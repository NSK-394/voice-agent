import os
import call_state
from models import VapiMessage
from typing import Optional

def _extract_client_id(call) -> str:
    cid = (call.metadata or {}).get("client_id")
    if cid:
        return cid
    overrides = call.assistantOverrides or {}
    cid = (overrides.get("metadata") or {}).get("client_id")
    return cid or "nikhil_test"

async def route_event(msg: VapiMessage) -> dict:
    handlers = {
        "call-started":       _handle_call_started,
        "end-of-call-report": _handle_end_of_call_report,
        "transcript":         _handle_transcript,
        "function-call":      _handle_function_call,
        "status-update":      _handle_status_update,
    }
    handler = handlers.get(msg.type)
    if handler is None:
        print(f"[vapi_handlers] Unknown event type: {msg.type}")
        return {"handled": False, "type": msg.type}
    return await handler(msg)


async def _handle_call_started(msg: VapiMessage) -> dict:
    call_id_str = msg.call.id
    lead_id = msg.call.metadata.get("lead_id", "unknown")
    phone = msg.call.customer.get("number", "")
    client_id = _extract_client_id(msg.call)

    existing_call_id = msg.call.metadata.get("db_call_id")
    if existing_call_id:
        call_state.mark_dialing(int(existing_call_id))
        db_id = int(existing_call_id)
    else:
        db_id = call_state.create_call(lead_id, phone, client_id)
        call_state.mark_dialing(db_id)

    print(f"[vapi_handlers] Handled: call-started for call {call_id_str} "
          f"(db_id={db_id}, lead={lead_id}, client={client_id})")
    return {"handled": True, "type": "call-started", "db_call_id": db_id}


async def _handle_end_of_call_report(msg: VapiMessage) -> dict:
    import qualification
    import sheets as sheets_module

    call_id_str = msg.call.id
    db_call_id = msg.call.metadata.get("db_call_id")
    client_id = _extract_client_id(msg.call)
    ended_reason = msg.endedReason or ""

    print(f"[vapi_handlers] Handled: end-of-call-report for call {call_id_str}, "
          f"reason={ended_reason}, client={client_id}")

    if db_call_id is None:
        print(f"[vapi_handlers] No db_call_id in metadata for call {call_id_str}, skipping state update")
        return {"handled": True, "type": "end-of-call-report", "skipped": True}

    db_call_id = int(db_call_id)

    no_answer_reasons = {"no-answer", "voicemail", "assistant-error", "customer-did-not-answer"}
    if ended_reason in no_answer_reasons:
        call_state.schedule_retry(db_call_id)
        print(f"[vapi_handlers] Scheduled retry for db_call_id={db_call_id}")
        return {"handled": True, "type": "end-of-call-report", "action": "retry_scheduled"}

    # Look up per-client config
    client = call_state.get_client(client_id)
    if client is None:
        print(f"[vapi_handlers] WARNING: client '{client_id}' not in DB, using defaults")
    system_prompt = client["system_prompt"] if client else None
    lead_destination_type = client["lead_destination_type"] if client else "google_sheet"
    lead_destination_value = (
        client["lead_destination_value"] if client
        else os.environ.get("GOOGLE_SHEETS_ID", "")
    )

    transcript = msg.transcript or ""
    result = qualification.qualify_transcript(transcript, db_call_id, system_prompt=system_prompt)

    if result.get("status") == "qualified" and lead_destination_value:
        try:
            if lead_destination_type == "webhook":
                await sheets_module.export_to_webhook(db_call_id, lead_destination_value)
            else:
                sheets_module.export_qualified_lead(db_call_id, lead_destination_value)
        except Exception as exc:
            print(f"[vapi_handlers] Export failed for call {db_call_id}: {exc}")

    print(f"[vapi_handlers] Qualified call {call_id_str}: intent={result.get('intent')}")
    return {"handled": True, "type": "end-of-call-report", "qualification": result}


async def _handle_transcript(msg: VapiMessage) -> dict:
    call_id_str = msg.call.id
    snippet = (msg.transcript or "")[:80]
    print(f"[vapi_handlers] Handled: transcript for call {call_id_str}: {snippet!r}")
    return {"handled": True, "type": "transcript"}


async def _handle_status_update(msg: VapiMessage) -> dict:
    call_id_str = msg.call.id
    status = msg.status or "unknown"
    print(f"[vapi_handlers] Handled: status-update for call {call_id_str}: status={status}")
    return {"handled": True, "type": "status-update", "status": status}


async def _handle_function_call(msg: VapiMessage) -> dict:
    import context_tool

    call_id_str = msg.call.id
    fn = msg.functionCall
    if fn is None:
        return {"handled": False, "error": "missing functionCall"}

    print(f"[vapi_handlers] Handled: function-call '{fn.name}' for call {call_id_str}")

    if fn.name == "fetch_live_data":
        query = fn.parameters.get("query", "")
        data = await context_tool.fetch_live_data(query)
        return {"result": data}

    print(f"[vapi_handlers] Unknown function: {fn.name}")
    return {"result": {"error": f"Unknown function: {fn.name}"}}


def _find_client_by_phone_number(phone_number_id: str) -> Optional[dict]:
    """Phase 3: look up a client by their provisioned Vapi inbound phone number ID."""
    for c in call_state.list_clients():
        if c.get("vapi_phone_number_id") == phone_number_id:
            return c
    return None
