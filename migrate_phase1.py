"""
Phase 1 migration — run ONCE before deploying updated app code.
    python migrate_phase1.py

Safe to re-run: all operations are idempotent.
Does NOT import call_state — uses raw sqlite3 directly.
"""
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_DB_PATH = Path(__file__).resolve().parent / "data" / "voice.db"

_SYSTEM_PROMPT_SEED = """\
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


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def run():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    print(f"[migrate] Connected to {_DB_PATH}")

    # Step 0: ensure calls table exists (safe on fresh DBs)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id          TEXT    NOT NULL,
            phone            TEXT    NOT NULL,
            status           TEXT    NOT NULL DEFAULT 'pending',
            attempt_count    INTEGER NOT NULL DEFAULT 0,
            last_attempt_at  TEXT,
            next_retry_at    TEXT,
            sentiment        TEXT,
            summary          TEXT,
            created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
    """)
    print("[migrate] calls table: OK")

    # Step 1: create clients table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id                TEXT PRIMARY KEY,
            business_name            TEXT NOT NULL,
            language                 TEXT NOT NULL DEFAULT 'en-IN',
            system_prompt            TEXT NOT NULL,
            lead_destination_type    TEXT,
            lead_destination_value   TEXT,
            direction                TEXT DEFAULT 'outbound',
            vapi_phone_number_id     TEXT,
            active                   INTEGER DEFAULT 1,
            created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[migrate] clients table: OK")

    # Step 2: add client_id column to calls if absent
    if not _column_exists(conn, "calls", "client_id"):
        conn.execute("ALTER TABLE calls ADD COLUMN client_id TEXT")
        print("[migrate] calls.client_id column: ADDED")
    else:
        print("[migrate] calls.client_id column: already exists")

    # Step 3: add direction column to calls if absent
    if not _column_exists(conn, "calls", "direction"):
        conn.execute("ALTER TABLE calls ADD COLUMN direction TEXT DEFAULT 'outbound'")
        print("[migrate] calls.direction column: ADDED")
    else:
        print("[migrate] calls.direction column: already exists")

    # Step 4: backfill existing rows
    updated = conn.execute(
        "UPDATE calls SET client_id = 'nikhil_test' WHERE client_id IS NULL"
    ).rowcount
    print(f"[migrate] Backfilled {updated} existing call rows with client_id='nikhil_test'")

    # Step 5: insert nikhil_test seed client (INSERT OR IGNORE = safe to re-run)
    google_sheets_id = os.environ.get("GOOGLE_SHEETS_ID", "")
    vapi_phone_number_id = os.environ.get("VAPI_PHONE_NUMBER_ID", "")

    conn.execute(
        """INSERT OR IGNORE INTO clients
           (client_id, business_name, language, system_prompt,
            lead_destination_type, lead_destination_value,
            direction, vapi_phone_number_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "nikhil_test",
            "Nikhil Test",
            "en-IN",
            _SYSTEM_PROMPT_SEED,
            "google_sheet",
            google_sheets_id,
            "outbound",
            vapi_phone_number_id,
        ),
    )
    print(f"[migrate] nikhil_test client seed: OK (sheet={google_sheets_id or '(empty)'})")

    conn.commit()
    conn.close()
    print("[migrate] Done. Phase 1 migration complete.")


if __name__ == "__main__":
    run()
