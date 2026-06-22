# Voice AI Agent — PRD

## Problem
Manually calling and qualifying leads doesn't scale. Sales reps spend hours on outbound calls where most leads don't answer or aren't a good fit. No-answer callbacks get forgotten. Qualified leads sit in notes instead of a structured list.

## Solution
A voice AI agent that calls leads automatically via Vapi, qualifies intent in real-time using Claude, fetches live company enrichment mid-call from Context.dev, retries no-answers on a schedule, and exports qualified leads to Google Sheets.

## Success Criteria
- Agent completes an outbound call end-to-end (dial → conversation → hang-up → state persisted)
- Correctly classifies lead intent as high / medium / low from the call transcript
- Retries no-answers on the ladder: 1 hr → 24 hr → 48 hr → dead (4 attempts max)
- Qualified leads appear as rows in a Google Sheet within seconds of call end
- `/leads` endpoint returns all call records as JSON

## Architecture
```
Vapi (voice platform)
  └── POST /webhook/vapi (FastAPI)
        ├── call-started   -> mark_dialing() in SQLite
        ├── function-call  -> fetch_live_data() via Context.dev
        ├── transcript     -> logged
        └── call-ended
              ├── no-answer/voicemail -> schedule_retry() (retry ladder)
              └── answered           -> Claude qualification -> Sheets export

POST /trigger-retry  (called by cron / n8n hourly)
  -> get_pending_retries() -> fire Vapi outbound call API

GET  /leads   -> SQLite read, JSON response
POST /leads   -> ingest a new lead (creates pending call record)
```

## Non-Goals (v1)
- No CRM integration (Salesforce, HubSpot)
- No multi-language support
- No analytics dashboard
- No inbound call handling
- No A/B testing of scripts

## Stack
| Layer | Tech |
|---|---|
| Voice | Vapi |
| Webhook server | FastAPI + uvicorn |
| Qualification LLM | Claude Haiku (claude-haiku-4-5-20251001) |
| Live enrichment | Context.dev REST API |
| State persistence | SQLite (WAL mode) |
| Lead export | Google Sheets API v4 |
| Retry trigger | n8n cron -> POST /trigger-retry |
| Deploy target | Hetzner VPS (same box as JARVIS/n8n) |

## Retry Ladder
| Attempt | Outcome | Next retry |
|---|---|---|
| 1 | no-answer | +1 hour |
| 2 | no-answer | +24 hours |
| 3 | no-answer | +48 hours |
| 4 | no-answer | status = dead (no further retries) |

## Environment Variables
See `.env.example` for the full list. Key ones:
- `VAPI_API_KEY` + `VAPI_PHONE_NUMBER_ID` + `VAPI_ASSISTANT_ID`
- `ANTHROPIC_API_KEY`
- `CONTEXT_DEV_API_KEY`
- `GOOGLE_SHEETS_ID` + `GOOGLE_SERVICE_ACCOUNT_JSON`
