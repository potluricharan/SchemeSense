"""Ingest the full `updated_data.csv` roster (3,400 schemes) into storage.

These rows are browse-able and searchable everywhere, but carry no verified
eligibility rules (free-text `eligibility` column), so `rules_verified=False`
and the optimizer ignores them. Use with the carefully hand-encoded schemes
from tools/curated_schemes.py for machine-checked eligibility.

Usage:
    python tools/ingest_dataset.py            # build data/scheme_roster.json
    python tools/ingest_dataset.py --sync     # also push to Firestore scheme_roster
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

CSV_PATH = PROJECT_ROOT / "updated_data.csv"
OUT_JSON = PROJECT_ROOT / "data" / "scheme_roster.json"

_ID_RE = re.compile(r"[^A-Za-z0-9._-]")

# Canonical state/UT names used for state-wise filtering.
ALL_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir",
    "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Delhi", "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu",
    "Ladakh", "Lakshadweep", "Puducherry",
]
_STATE_ALIASES = {
    "jammu & kashmir": "Jammu and Kashmir",
    "j&k": "Jammu and Kashmir",
    "andaman & nicobar": "Andaman and Nicobar Islands",
    "daman & diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra & nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "west bengal": "West Bengal",
}


def extract_states(text: str) -> list[str]:
    """Return canonical state names mentioned anywhere in the given text."""
    if not text:
        return []
    low = text.lower()
    found: list[str] = []
    for s in ALL_STATES:
        if s.lower() in low:
            found.append(s)
    for alias, canon in _STATE_ALIASES.items():
        if alias in low and canon not in found:
            found.append(canon)
    return found


def sanitize_id(slug: str) -> str:
    sid = _ID_RE.sub("-", slug or "").strip("-")
    return (sid or "slug")[:150]


def build_rows(df: pd.DataFrame) -> list[dict]:
    rows = []
    seen: set[str] = set()
    skipped = 0
    for _, r in df.iterrows():
        name = str(r.get("scheme_name", "")).strip()
        if not name or not str(r.get("slug", "")).strip():
            skipped += 1
            continue
        sid = sanitize_id(str(r["slug"]))
        if sid in seen:  # source CSV contains exact duplicate rows (same slug + name)
            skipped += 1
            continue
        seen.add(sid)
        docs = str(r.get("documents", "") or "")
        tags = [t.strip() for t in str(r.get("tags", "") or "").split(",") if t.strip()]
        level = str(r.get("level", "") or "").strip() or "State"
        mentioned = extract_states(" ".join([
            str(r.get("scheme_name", "") or ""),
            str(r.get("details", "") or ""),
            str(r.get("eligibility", "") or ""),
            str(r.get("benefits", "") or ""),
        ]))
        scheme = {
            "scheme_id": sid,
            "name": name,
            "level": level,
            "category": _categories(str(r.get("schemeCategory", "") or "")),
            "state": mentioned[0] if mentioned else ("any" if level == "Central" else "any"),
            "states": mentioned,
            "description": str(r.get("details", "") or "")[:2000],
            "eligibility_text": str(r.get("eligibility", "") or "")[:1000],
            "benefits": str(r.get("benefits", "") or "")[:800],
            "application": str(r.get("application", "") or "")[:1200],
            "documents": [d.strip() for d in docs.split(".") if len(d.strip()) > 4][:12],
            "tags": tags[:10],
            "rules_verified": False,
            "source": "updated_data.csv",
        }
        rows.append(scheme)
    if skipped:
        print(f"[info] skipped {skipped} duplicate/blank CSV rows")
    return rows


def _categories(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    return parts[:3] or ["General"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", action="store_true", help="push to Firestore too")
    args = parser.parse_args()

    df = pd.read_csv(CSV_PATH, encoding="utf-8", on_bad_lines="skip")
    rows = build_rows(df)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False)
    print(f"[ok] built roster of {len(rows)} schemes -> {OUT_JSON}")

    by_level = dict(df["level"].value_counts())
    print(f"levels: {by_level}")

    with_states = sum(1 for r in rows if r.get("states"))
    print(f"state coverage: {with_states}/{len(rows)} rows mention a state")

    if args.sync:
        from core.db import get_store

        n = get_store().upsert_roster(rows)
        print(f"[ok] pushed {n} roster entries to backend '{get_store().backend}'")


if __name__ == "__main__":
    main()