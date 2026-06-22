import json
from openai import OpenAI

import call_state

_SYSTEM_PROMPT = """\
You are a sales qualification assistant. You receive a transcript from an outbound sales call.
Classify the lead's intent and summarize the outcome.

Respond ONLY with valid JSON in this exact shape:
{"intent": "high" | "medium" | "low", "summary": "<one sentence, 30 words or fewer>"}

Intent definitions:
  high   - Lead expressed clear interest, asked follow-up questions, or agreed to a next step.
  medium - Lead was polite but non-committal, or needs more information before deciding.
  low    - Lead is not interested, has no budget, wrong timing, or asked to be removed.

Do not add any text outside the JSON object.\
"""


def qualify_transcript(transcript: str, call_id: int) -> dict:
    from config import get_settings
    import sheets

    settings = get_settings()
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=150,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Transcript:\n{transcript}"},
            ],
        )
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        intent = result.get("intent", "low")
        summary = result.get("summary", "")
    except json.JSONDecodeError:
        print(f"[qualification] JSON parse failed for call {call_id}, marking disqualified")
        call_state.update_outcome(call_id, "disqualified", None, "qualification_parse_failed")
        return {"intent": "low", "summary": "qualification_parse_failed"}
    except Exception as exc:
        print(f"[qualification] Error qualifying call {call_id}: {exc}")
        call_state.update_outcome(call_id, "disqualified", None, f"error: {exc}")
        return {"intent": "low", "summary": str(exc)}

    status = "qualified" if intent in ("high", "medium") else "disqualified"
    call_state.update_outcome(call_id, status, sentiment=intent, summary=summary)

    if status == "qualified":
        try:
            sheets.export_qualified_lead(call_id)
        except Exception as exc:
            print(f"[qualification] Sheets export failed for call {call_id}: {exc}")

    print(f"[qualification] call {call_id}: intent={intent}, status={status}, summary={summary!r}")
    return {"intent": intent, "summary": summary, "status": status}
