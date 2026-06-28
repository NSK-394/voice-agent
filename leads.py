import call_state
from models import LeadIn


def ingest_lead(lead: LeadIn) -> dict:
    call_id = call_state.create_call(lead.lead_id, lead.phone, lead.client_id)
    return {"call_id": call_id, "lead_id": lead.lead_id, "status": "pending"}


def list_leads() -> list[dict]:
    return call_state.list_all_calls()
