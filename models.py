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
    transcript: Optional[str] = None
    functionCall: Optional[VapiFunctionCall] = None
    endedReason: Optional[str] = None
    artifact: Optional[dict] = None

class VapiWebhookPayload(BaseModel):
    message: VapiMessage

class LeadIn(BaseModel):
    lead_id: str
    phone: str
    name: Optional[str] = None
    company: Optional[str] = None
