"""Per-family scheme registration tracker (simple local JSONL persistence).

Kept deliberately lightweight: it stores which schemes a household has applied
for and the current status on disk. Works identically on the local and
Firestore-degraded backends without adding cloud round-trips.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from core import config

REG_FILE: Path = config.PROJECT_ROOT / "data" / "local_db" / "registrations.jsonl"

STATUSES = [
    "Not started",
    "Applying / submitted",
    "Under review",
    "Approved",
    "Rejected",
    "Need more documents",
]


def _rows() -> list[dict]:
    if not REG_FILE.exists():
        return []
    out = []
    for line in open(REG_FILE, "r", encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _write(rows: list[dict]) -> None:
    REG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REG_FILE, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def list_registrations(profile_id: str | None = None, scheme_id: str | None = None) -> list[dict]:
    rows = _rows()
    if profile_id:
        rows = [r for r in rows if r.get("profile_id") == profile_id]
    if scheme_id:
        rows = [r for r in rows if r.get("scheme_id") == scheme_id]
    rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
    return rows


def add_registration(profile_id: str, scheme_id: str, scheme_name: str, note: str = "") -> str:
    rid = f"reg_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    row = {
        "id": rid,
        "profile_id": profile_id or "local",
        "scheme_id": scheme_id,
        "scheme_name": scheme_name,
        "status": "Not started",
        "note": note,
        "ts": time.time(),
    }
    with open(REG_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rid


def update_registration(reg_id: str, status: str, note: str) -> bool:
    rows = _rows()
    found = False
    for r in rows:
        if r.get("id") == reg_id:
            r["status"] = status
            r["note"] = note
            r["updated_ts"] = time.time()
            found = True
    if not found:
        return False
    _write(rows)
    return True


def delete_registration(reg_id: str) -> None:
    _write([r for r in _rows() if r.get("id") != reg_id])