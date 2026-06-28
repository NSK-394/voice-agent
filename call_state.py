import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).resolve().parent / "data" / "voice.db"
_lock = threading.Lock()

_RETRY_HOURS = {1: 1, 2: 24, 3: 48}  # attempt_count -> hours until next retry

def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_next_retry_at ON calls(next_retry_at)")
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
    # Safe migrations — idempotent, run on every startup
    existing_cols = {r[1] for r in conn.execute("PRAGMA table_info(calls)").fetchall()}
    if "client_id" not in existing_cols:
        conn.execute("ALTER TABLE calls ADD COLUMN client_id TEXT")
    if "direction" not in existing_cols:
        conn.execute("ALTER TABLE calls ADD COLUMN direction TEXT DEFAULT 'outbound'")
    conn.commit()
    return conn

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _delta_iso(hours: float) -> str:
    dt = datetime.now(timezone.utc) + timedelta(hours=hours)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# ── Calls ─────────────────────────────────────────────────────────────────────

def create_call(lead_id: str, phone: str, client_id: str = "nikhil_test") -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO calls (lead_id, phone, client_id) VALUES (?, ?, ?)",
            (lead_id, phone, client_id),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
    return row_id

def mark_dialing(call_id: int) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            """UPDATE calls
               SET status = 'dialing',
                   attempt_count = attempt_count + 1,
                   last_attempt_at = ?
               WHERE id = ?""",
            (_now_iso(), call_id),
        )
        conn.commit()
        conn.close()

def schedule_retry(call_id: int) -> None:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT attempt_count FROM calls WHERE id = ?", (call_id,)
        ).fetchone()
        if row is None:
            conn.close()
            return
        attempt = row["attempt_count"]
        if attempt in _RETRY_HOURS:
            conn.execute(
                """UPDATE calls
                   SET status = 'no_answer',
                       next_retry_at = ?
                   WHERE id = ?""",
                (_delta_iso(_RETRY_HOURS[attempt]), call_id),
            )
        else:
            conn.execute(
                """UPDATE calls
                   SET status = 'dead',
                       next_retry_at = NULL
                   WHERE id = ?""",
                (call_id,),
            )
        conn.commit()
        conn.close()

def update_outcome(
    call_id: int,
    status: str,
    sentiment: Optional[str] = None,
    summary: Optional[str] = None,
) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            """UPDATE calls
               SET status = ?, sentiment = ?, summary = ?, next_retry_at = NULL
               WHERE id = ?""",
            (status, sentiment, summary, call_id),
        )
        conn.commit()
        conn.close()

def get_call(call_id: int) -> Optional[dict]:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
        conn.close()
    return dict(row) if row else None

def get_pending_retries() -> list[dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            """SELECT * FROM calls
               WHERE status = 'no_answer'
                 AND next_retry_at <= strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"""
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]

def get_pending_initial() -> list[dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM calls WHERE status = 'pending'"
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]

def list_all_calls() -> list[dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM calls ORDER BY id DESC").fetchall()
        conn.close()
    return [dict(r) for r in rows]

# ── Clients ───────────────────────────────────────────────────────────────────

def create_client(
    client_id: str,
    business_name: str,
    language: str,
    system_prompt: str,
    lead_destination_type: Optional[str],
    lead_destination_value: Optional[str],
    direction: str = "outbound",
    vapi_phone_number_id: Optional[str] = None,
) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            """INSERT INTO clients
               (client_id, business_name, language, system_prompt,
                lead_destination_type, lead_destination_value,
                direction, vapi_phone_number_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (client_id, business_name, language, system_prompt,
             lead_destination_type, lead_destination_value,
             direction, vapi_phone_number_id),
        )
        conn.commit()
        conn.close()

def get_client(client_id: str) -> Optional[dict]:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT * FROM clients WHERE client_id = ?", (client_id,)
        ).fetchone()
        conn.close()
    return dict(row) if row else None

def list_clients() -> list[dict]:
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM clients ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]

def update_client_phone(client_id: str, vapi_phone_number_id: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE clients SET vapi_phone_number_id = ? WHERE client_id = ?",
            (vapi_phone_number_id, client_id),
        )
        conn.commit()
        conn.close()
