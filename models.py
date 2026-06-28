from pydantic import BaseModel
from typing import Literal, Optional

CallStatus = Literal[
    "pending", "dialing", "answered", "no_answer",
    "qualified", "disqualified", "dead"
]

class VapiCall(BaseModel):
    id: str
    customer: dict = {}
    metadata: dict = {}

class VapiFunctionCall(BaseModel):
    name: str
    parameters: dict = {}

class VapiMessage(BaseModel):
    type: str
    call: VapiCall
    transcript: Optional[str] = None      # full transcript on end-of-call-report; partial on transcript events
    summary: Optional[str] = None         # Vapi's own AI summary, present on end-of-call-report
    functionCall: Optional[VapiFunctionCall] = None
    endedReason: Optional[str] = None     # present on end-of-call-report
    status: Optional[str] = None          # present on status-update events
    artifact: Optional[dict] = None       # legacy field, kept for compatibility

class VapiWebhookPayload(BaseModel):
    message: VapiMessage

class LeadIn(BaseModel):
    lead_id: str
    phone: str
    name: Optional[str] = None
    company: Optional[str] = None
    client_id: str = "nikhil_test"

class ClientIn(BaseModel):
    client_id: str
    business_name: str
    language: str = "en-IN"
    system_prompt: str
    lead_destination_type: Optional[str] = "google_sheet"
    lead_destination_value: Optional[str] = None
    direction: str = "outbound"
    vapi_phone_number_id: Optional[str] = None
