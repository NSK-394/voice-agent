"""
Unit test for the call state retry ladder.
Run: python tests/test_call_state.py
"""
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Patch DB path before importing call_state so tests use a throwaway DB
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import call_state

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
call_state._DB_PATH = Path(_tmp.name)
_tmp.close()


def _parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def test_retry_ladder():
    cid = call_state.create_call("lead_test", "+14155550001")
    now = datetime.now(timezone.utc)

    # Attempt 1 → no_answer, next_retry ~1h
    call_state.mark_dialing(cid)
    call_state.schedule_retry(cid)
    row = call_state.get_call(cid)
    assert row["status"] == "no_answer", f"Expected no_answer, got {row['status']}"
    assert row["next_retry_at"] is not None
    delta = _parse_iso(row["next_retry_at"]) - now
    assert 3590 < delta.total_seconds() < 3610, f"Expected ~1h, got {delta}"
    print(f"  Attempt 1: next_retry in {delta} OK")

    # Attempt 2 → no_answer, next_retry ~24h
    call_state.mark_dialing(cid)
    call_state.schedule_retry(cid)
    row = call_state.get_call(cid)
    assert row["status"] == "no_answer"
    delta = _parse_iso(row["next_retry_at"]) - now
    assert 86390 < delta.total_seconds() < 86410, f"Expected ~24h, got {delta}"
    print(f"  Attempt 2: next_retry in {delta} OK")

    # Attempt 3 → no_answer, next_retry ~48h
    call_state.mark_dialing(cid)
    call_state.schedule_retry(cid)
    row = call_state.get_call(cid)
    assert row["status"] == "no_answer"
    delta = _parse_iso(row["next_retry_at"]) - now
    assert 172790 < delta.total_seconds() < 172810, f"Expected ~48h, got {delta}"
    print(f"  Attempt 3: next_retry in {delta} OK")

    # Attempt 4 → dead
    call_state.mark_dialing(cid)
    call_state.schedule_retry(cid)
    row = call_state.get_call(cid)
    assert row["status"] == "dead", f"Expected dead, got {row['status']}"
    assert row["next_retry_at"] is None, f"Expected NULL next_retry_at, got {row['next_retry_at']}"
    assert row["attempt_count"] == 4
    print(f"  Attempt 4: status=dead, next_retry_at=NULL OK")

    print("\n[PASS] Retry ladder: 3 no-answers -> dead on attempt 4")


def test_update_outcome():
    cid = call_state.create_call("lead_qual", "+14155550002")
    call_state.mark_dialing(cid)
    call_state.update_outcome(cid, "qualified", sentiment="high", summary="Very interested, asked for demo.")
    row = call_state.get_call(cid)
    assert row["status"] == "qualified"
    assert row["sentiment"] == "high"
    assert row["summary"] == "Very interested, asked for demo."
    assert row["next_retry_at"] is None
    print("[PASS] update_outcome: qualified lead written correctly")


def test_pending_retries():
    cid = call_state.create_call("lead_retry", "+14155550003")
    call_state.mark_dialing(cid)
    # Manually set next_retry_at to the past
    import sqlite3
    conn = sqlite3.connect(str(call_state._DB_PATH))
    conn.execute(
        "UPDATE calls SET status='no_answer', next_retry_at=? WHERE id=?",
        ("2000-01-01T00:00:00Z", cid),
    )
    conn.commit()
    conn.close()

    pending = call_state.get_pending_retries()
    ids = [r["id"] for r in pending]
    assert cid in ids, f"Expected call {cid} in pending retries, got {ids}"
    print("[PASS] get_pending_retries: past next_retry_at returned correctly")


if __name__ == "__main__":
    test_retry_ladder()
    test_update_outcome()
    test_pending_retries()
    print("\nAll tests passed.")
