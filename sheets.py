import httpx
from datetime import datetime, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

import call_state

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_SHEET_RANGE = "Sheet1"
_COLUMNS = ["call_id", "lead_id", "phone", "intent", "summary",
            "attempt_count", "exported_at", "call_ended_at"]


def _get_service():
    from config import get_settings
    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_JSON,
        scopes=_SCOPES,
    )
    return build("sheets", "v4", credentials=creds)


def ensure_header(sheet_id: str) -> None:
    service = _get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{_SHEET_RANGE}!A1:H1",
    ).execute()
    existing = result.get("values", [])
    if not existing:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{_SHEET_RANGE}!A1",
            valueInputOption="RAW",
            body={"values": [_COLUMNS]},
        ).execute()
        print(f"[sheets] Header row written to sheet {sheet_id}")


def export_qualified_lead(call_id: int, sheet_id: str) -> None:
    row = call_state.get_call(call_id)
    if row is None:
        print(f"[sheets] Call {call_id} not found, skipping export")
        return

    exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    values = [[
        row["id"],
        row["lead_id"],
        row["phone"],
        row.get("sentiment", ""),
        row.get("summary", ""),
        row["attempt_count"],
        exported_at,
        row.get("last_attempt_at", ""),
    ]]

    service = _get_service()
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{_SHEET_RANGE}!A:H",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()
    print(f"[sheets] Exported call {call_id} (lead={row['lead_id']}) to sheet {sheet_id}")


async def export_to_webhook(call_id: int, webhook_url: str) -> None:
    row = call_state.get_call(call_id)
    if row is None:
        print(f"[sheets] Call {call_id} not found, skipping webhook export")
        return

    payload = {
        "call_id": row["id"],
        "lead_id": row["lead_id"],
        "phone": row["phone"],
        "intent": row.get("sentiment", ""),
        "summary": row.get("summary", ""),
        "attempt_count": row["attempt_count"],
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "call_ended_at": row.get("last_attempt_at", ""),
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()
    print(f"[sheets] Webhook export for call {call_id} to {webhook_url}: OK")
