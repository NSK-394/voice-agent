import call_state
from models import VapiMessage

async def route_event(msg: VapiMessage) -> dict:
    handlers = {
        "call-started":  _handle_call_started,
        "end-of-call-report":    _handle_call_ended,
        "transcript":    _handle_transcript,
        "function-call": _handle_function_call,
    }
    handler = handlers.get(msg.type)
    if handler is None:
        print(f"[vapi_handlers] Unknown event type: {msg.type}")
        return {"handled": False, "type": msg.type}
    return await handler(msg)
async def _handle_status_update(msg: VapiMessage) -> dict:
    print(f"[vapi_handlers] status-update: {msg.call.id}")
    return {"handled": True, "type": "status-update"}


async def _handle_call_started(msg: VapiMessage) -> dict:
    call_id_str = msg.call.id
    lead_id = msg.call.metadata.get("lead_id", "unknown")
    phone = msg.call.customer.get("number", "")

    existing_call_id = msg.call.metadata.get("db_call_id")
    if existing_call_id:
        call_state.mark_dialing(int(existing_call_id))
        db_id = int(existing_call_id)
    else:
        db_id = call_state.create_call(lead_id, phone)
        call_state.mark_dialing(db_id)

    print(f"[vapi_handlers] Handled: call-started for call {call_id_str} (db_id={db_id}, lead={lead_id})")
    return {"handled": True, "type": "call-started", "db_call_id": db_id}


async def _handle_call_ended(msg: VapiMessage) -> dict:
    import qualification

    call_id_str = msg.call.id
    db_call_id = msg.call.metadata.get("db_call_id")
    ended_reason = msg.endedReason or ""

    print(f"[vapi_handlers] Handled: call-ended for call {call_id_str}, reason={ended_reason}")

    if db_call_id is None:
        print(f"[vapi_handlers] No db_call_id in metadata for call {call_id_str}, skipping state update")
        return {"handled": True, "type": "call-ended", "skipped": True}

    db_call_id = int(db_call_id)

    no_answer_reasons = {"no-answer", "voicemail", "assistant-error", "customer-did-not-answer"}
    if ended_reason in no_answer_reasons:
        call_state.schedule_retry(db_call_id)
        print(f"[vapi_handlers] Scheduled retry for db_call_id={db_call_id}")
        return {"handled": True, "type": "call-ended", "action": "retry_scheduled"}

    transcript = ""
    if msg.artifact:
        transcript = msg.artifact.get("transcript", "")
    if not transcript and msg.transcript:
        transcript = msg.transcript

    result = qualification.qualify_transcript(transcript, db_call_id)
    print(f"[vapi_handlers] Qualified call {call_id_str}: intent={result.get('intent')}")
    return {"handled": True, "type": "call-ended", "qualification": result}


async def _handle_transcript(msg: VapiMessage) -> dict:
    call_id_str = msg.call.id
    snippet = (msg.transcript or "")[:80]
    print(f"[vapi_handlers] Handled: transcript for call {call_id_str}: {snippet!r}")
    return {"handled": True, "type": "transcript"}


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
