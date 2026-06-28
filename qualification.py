import json
from openai import OpenAI
from typing import Optional

import call_state

# Kept as fallback for backward compatibility and the nikhil_test seed client
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


def qualify_transcript(
    transcript: str,
    call_id: int,
    system_prompt: Optional[str] = None,
) -> dict:
    from config import get_settings

    settings = get_settings()
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    prompt_to_use = system_prompt if system_prompt is not None else _SYSTEM_PROMPT

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=150,
            messages=[
                {"role": "system", "content": prompt_to_use},
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
        return {"intent": "low", "summary": "qualification_parse_failed", "status": "disqualified"}
    except Exception as exc:
        print(f"[qualification] Error qualifying call {call_id}: {exc}")
        call_state.update_outcome(call_id, "disqualified", None, f"error: {exc}")
        return {"intent": "low", "summary": str(exc), "status": "disqualified"}

    status = "qualified" if intent in ("high", "medium") else "disqualified"
    call_state.update_outcome(call_id, status, sentiment=intent, summary=summary)

    print(f"[qualification] call {call_id}: intent={intent}, status={status}, summary={summary!r}")
    return {"intent": intent, "summary": summary, "status": status}
