# Voice AI Agent

An automated outbound voice AI system that calls leads, qualifies their intent in real time, and exports results to Google Sheets — eliminating the manual effort of cold-call qualification at scale. Built with [Vapi](https://vapi.ai) for voice, [Context.dev](https://context.dev) for live company enrichment mid-call, and OpenAI GPT-4o-mini for intent classification. Built as part of a Founders Lab cohort project.

---

## Architecture

```
You → POST /leads
        │
        ▼
  SQLite (call state)
        │
POST /trigger-retry (cron via n8n)
        │
        ▼
   Vapi outbound call API
        │
        ▼
   Lead's phone rings
        │
   ┌────┴─────────────────────────────────┐
   │           During call                │
   │  function-call → Context.dev         │
   │  (live company enrichment)           │
   └────┬─────────────────────────────────┘
        │
   Call ends → end-of-call-report webhook
        │
        ├── no-answer → retry ladder (1h → 24h → 48h → dead)
        │
        └── answered → GPT-4o-mini classifies transcript
                            │
                    high / medium → qualified → Google Sheets row
                    low           → disqualified → SQLite only
```

---

## Tech Stack

| Layer | Tool |
|---|---|
| Voice calls | [Vapi](https://vapi.ai) |
| Live enrichment | [Context.dev](https://context.dev) API |
| Qualification LLM | OpenAI GPT-4o-mini |
| Webhook server | FastAPI + uvicorn |
| Call state | SQLite (WAL mode, no ORM) |
| Lead export | Google Sheets API v4 |
| Process manager | pm2 |
| Tunnel | Cloudflare Tunnel |

---

## Key Features

- **Webhook routing** — handles `call-started`, `end-of-call-report`, `transcript`, `function-call`, and `status-update` events from Vapi
- **Live enrichment** — Vapi calls `fetch_live_data()` mid-conversation via a registered function tool; Context.dev returns real-time company data the AI uses to qualify
- **Retry ladder** — no-answer calls are retried automatically: +1 hr → +24 hr → +48 hr → marked dead on the 4th miss
- **AI qualification** — GPT-4o-mini classifies transcript intent as `high / medium / low` with a one-line summary; high and medium go to Sheets
- **Webhook signature verification** — HMAC-SHA256 check on incoming Vapi webhooks (opt-in via `VAPI_WEBHOOK_SECRET`)
- **REST API** — `GET /leads` returns the full pipeline as JSON; `POST /leads` ingests a new lead

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/NSK-394/voice-agent.git
cd voice-agent
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in all values in .env — see .env.example for the full list
```

Required keys:

| Variable | Where to get it |
|---|---|
| `VAPI_API_KEY` | [Vapi dashboard](https://dashboard.vapi.ai) → API Keys |
| `VAPI_PHONE_NUMBER_ID` | Vapi dashboard → Phone Numbers → copy the resource UUID |
| `VAPI_ASSISTANT_ID` | Vapi dashboard → Assistants |
| `VAPI_WEBHOOK_SECRET` | Vapi dashboard → Server URL settings (optional) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| `CONTEXT_DEV_API_KEY` | [context.dev](https://context.dev) |
| `GOOGLE_SHEETS_ID` | The ID portion of your Sheet URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Path to your GCP service account JSON file |

### 3. Google Sheets setup

- Create a GCP service account and download the JSON key → save as `service_account.json` in the project root
- Share your Google Sheet with the service account email (Editor access)
- Run once to write the header row: `python -c "from sheets import ensure_header; ensure_header()"`

### 4. Run locally

```bash
python main.py
# Server starts at http://localhost:8000
# Docs at http://localhost:8000/docs
```

Expose it to Vapi using [ngrok](https://ngrok.com) or Cloudflare Tunnel:
```bash
cloudflared tunnel --url http://localhost:8000
```

Set the resulting URL as your Vapi assistant's **Server URL** in the Vapi dashboard.

### 5. Register the Context.dev tool in Vapi

In the Vapi dashboard, add a function tool to your assistant with this schema (see `context_tool.py` → `get_tool_schema()`):

```json
{
  "type": "function",
  "function": {
    "name": "fetch_live_data",
    "description": "Fetches live company enrichment from Context.dev",
    "parameters": {
      "type": "object",
      "properties": { "query": { "type": "string" } },
      "required": ["query"]
    }
  }
}
```

---

## Deployment (Hetzner VPS + pm2)

```bash
# On the VPS
git clone https://github.com/NSK-394/voice-agent.git
cd voice-agent
pip install -r requirements.txt
cp .env.example .env && nano .env   # fill in real keys

pm2 start "python main.py" --name voice-agent
pm2 save

# Set up n8n cron: hourly trigger → POST http://localhost:8000/trigger-retry
```

Point Vapi's Server URL at your VPS via Cloudflare Tunnel.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhook/vapi` | Receives all Vapi webhook events |
| `POST` | `/leads` | Ingest a new lead (creates pending call record) |
| `GET` | `/leads` | List all calls and their current status |
| `POST` | `/trigger-retry` | Fire outbound calls for all due retries |

---

## Project Structure

```
voice-agent/
├── main.py              # FastAPI app + /trigger-retry logic
├── vapi_handlers.py     # Webhook event router
├── qualification.py     # GPT-4o-mini intent classification
├── context_tool.py      # Context.dev enrichment tool
├── call_state.py        # SQLite state machine
├── leads.py             # Lead ingestion
├── sheets.py            # Google Sheets export
├── models.py            # Pydantic webhook models
├── config.py            # Environment config
├── tests/
│   └── test_call_state.py
├── .env.example
└── PRD.md               # Internal planning doc
```

---

## License

MIT
