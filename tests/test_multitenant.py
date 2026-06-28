"""
Multi-tenant integration test — Phase 1 sanity checks.

Tests two things:
  1. client_id round-trip: VapiWebhookPayload with metadata.client_id is parsed
     correctly and vapi_handlers extracts it, looks up the right client, and
     passes that client's system_prompt to qualification.
  2. Client isolation: two clients with different system_prompts and sheet IDs
     each see only their own config — no cross-contamination.

Run: python tests/test_multitenant.py
"""
import sys
import json
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import call_state

# Redirect DB to a fresh throwaway file before any other imports touch call_state
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
call_state._DB_PATH = Path(_tmp.name)
_tmp.close()

import vapi_handlers
from models import VapiWebhookPayload


# ─── Fixtures ────────────────────────────────────────────────────────────────

_PROMPT_CLIENT_1 = "You qualify English leads. Respond ONLY with JSON {\"intent\":\"high\"|\"medium\"|\"low\",\"summary\":\"...\"}."
_PROMPT_CLIENT_2 = "Tum Hindi leads qualify karo. Sirf JSON mein jawab do {\"intent\":\"high\"|\"medium\"|\"low\",\"summary\":\"...\"}."

def _setup_clients():
    call_state.create_client(
        client_id="nikhil_test",
        business_name="Nikhil Test",
        language="en-IN",
        system_prompt=_PROMPT_CLIENT_1,
        lead_destination_type="google_sheet",
        lead_destination_value="SHEET_ID_CLIENT_1",
        direction="outbound",
        vapi_phone_number_id="phone-uuid-client-1",
    )
    call_state.create_client(
        client_id="test_client_2",
        business_name="Test Client 2",
        language="hi-IN",
        system_prompt=_PROMPT_CLIENT_2,
        lead_destination_type="google_sheet",
        lead_destination_value="SHEET_ID_CLIENT_2",
        direction="outbound",
        vapi_phone_number_id="phone-uuid-client-2",
    )
    print("[setup] Created nikhil_test and test_client_2 clients in temp DB")


def _make_end_of_call_payload(client_id: str, db_call_id: int) -> str:
    """Build the exact JSON structure Vapi sends for end-of-call-report."""
    return json.dumps({
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": f"vapi-call-{client_id}-001",
                "customer": {"number": "+919999999999"},
                "metadata": {
                    "lead_id": f"lead_{client_id}",
                    "db_call_id": str(db_call_id),
                    "client_id": client_id,
                },
            },
            "transcript": "Agent: Hi, are you interested in our product?\nCustomer: Yes, tell me more.",
            "endedReason": "customer-ended-call",
        }
    })


# ─── Tests ───────────────────────────────────────────────────────────────────

def test_payload_parsing():
    """VapiWebhookPayload correctly parses metadata.client_id from Vapi JSON."""
    raw = _make_end_of_call_payload("nikhil_test", 99)
    payload = VapiWebhookPayload.model_validate_json(raw)
    msg = payload.message

    assert msg.type == "end-of-call-report", f"Wrong type: {msg.type}"
    assert msg.call.metadata.get("client_id") == "nikhil_test", \
        f"client_id missing from parsed metadata: {msg.call.metadata}"
    assert msg.call.metadata.get("db_call_id") == "99", \
        f"db_call_id not preserved: {msg.call.metadata}"
    assert msg.endedReason == "customer-ended-call"
    print("[PASS] Payload parsing: metadata.client_id round-trips correctly through Pydantic model")


def test_client_isolation():
    """
    Two calls, two different clients — each handler invocation uses only that
    client's system_prompt. Captured via mock on qualification.qualify_transcript.
    """
    captured = {}  # client_id -> system_prompt used

    def fake_qualify(transcript, call_id, system_prompt=None):
        # Record which prompt was used for this call_id
        captured[call_id] = system_prompt
        return {"intent": "high", "summary": "Interested.", "status": "qualified"}

    def fake_export(call_id, sheet_id):
        pass  # suppress actual Google Sheets call

    # Create call rows for each client
    cid_1 = call_state.create_call("lead_nikhil", "+911111111111", "nikhil_test")
    cid_2 = call_state.create_call("lead_client2", "+912222222222", "test_client_2")

    payload_1 = VapiWebhookPayload.model_validate_json(
        _make_end_of_call_payload("nikhil_test", cid_1)
    )
    payload_2 = VapiWebhookPayload.model_validate_json(
        _make_end_of_call_payload("test_client_2", cid_2)
    )

    with patch("qualification.qualify_transcript", side_effect=fake_qualify), \
         patch("sheets.export_qualified_lead", side_effect=fake_export):
        asyncio.run(vapi_handlers.route_event(payload_1.message))
        asyncio.run(vapi_handlers.route_event(payload_2.message))

    assert cid_1 in captured, f"Handler never called qualify for cid_1={cid_1}"
    assert cid_2 in captured, f"Handler never called qualify for cid_2={cid_2}"

    assert captured[cid_1] == _PROMPT_CLIENT_1, (
        f"nikhil_test got wrong prompt.\n"
        f"Expected: {_PROMPT_CLIENT_1!r}\n"
        f"Got:      {captured[cid_1]!r}"
    )
    assert captured[cid_2] == _PROMPT_CLIENT_2, (
        f"test_client_2 got wrong prompt.\n"
        f"Expected: {_PROMPT_CLIENT_2!r}\n"
        f"Got:      {captured[cid_2]!r}"
    )
    assert captured[cid_1] != captured[cid_2], \
        "ISOLATION FAILURE: both clients used the same system_prompt"

    print(f"[PASS] Client isolation: nikhil_test used its own prompt (English)")
    print(f"[PASS] Client isolation: test_client_2 used its own prompt (Hindi)")
    print(f"[PASS] The two prompts are different — no cross-contamination")


def test_missing_client_fallback():
    """Handler falls back gracefully if client_id is not in the DB."""
    cid = call_state.create_call("lead_unknown", "+913333333333", "nonexistent_client")

    raw = json.dumps({
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "vapi-call-ghost-001",
                "customer": {"number": "+913333333333"},
                "metadata": {
                    "lead_id": "lead_unknown",
                    "db_call_id": str(cid),
                    "client_id": "nonexistent_client",
                },
            },
            "transcript": "Short call.",
            "endedReason": "customer-ended-call",
        }
    })
    payload = VapiWebhookPayload.model_validate_json(raw)

    def fake_qualify(transcript, call_id, system_prompt=None):
        return {"intent": "low", "summary": "Short.", "status": "disqualified"}

    with patch("qualification.qualify_transcript", side_effect=fake_qualify) as mock_q:
        result = asyncio.run(vapi_handlers.route_event(payload.message))

    # Should not raise; should still call qualify (with None prompt = _SYSTEM_PROMPT fallback)
    assert result.get("handled") is True
    assert mock_q.called
    _, kwargs = mock_q.call_args
    assert kwargs.get("system_prompt") is None, \
        f"Expected None prompt for missing client, got {kwargs.get('system_prompt')!r}"
    print("[PASS] Missing client fallback: handler completes without crash, passes None prompt")


if __name__ == "__main__":
    _setup_clients()
    print()
    test_payload_parsing()
    test_client_isolation()
    test_missing_client_fallback()
    print("\nAll multi-tenant checks passed.")
