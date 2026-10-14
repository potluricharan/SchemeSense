"""Seed the scheme_rules table.

Builds `data/scheme_rules.json` (and pushes to Firestore when credentials exist)
from the curated machine-readable rules (tools/curated_schemes.py) enriched with
description / documents / tags from `updated_data.csv`.

Usage:
    python tools/seed_schemes.py            # build JSON only
    python tools/seed_schemes.py --sync     # also write to Firestore scheme_rules
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from core import config  # noqa: E402
from tools.curated_schemes import CURATED_SCHEMES  # noqa: E402

CSV_PATH = PROJECT_ROOT / "updated_data.csv"
OUT_JSON = PROJECT_ROOT / "data" / "scheme_rules.json"


def load_csv() -> pd.DataFrame:
    return pd.read_csv(CSV_PATH, encoding="utf-8", on_bad_lines="skip")


def enrich(lookup: pd.DataFrame, curated: list[dict]) -> list[dict]:
    out = []
    for s in curated:
        slug = s.get("csv_slug")
        row = None
        if slug:
            match = lookup[lookup["slug"] == slug]
            if not match.empty:
                row = match.iloc[0]
        rec = dict(s)
        if row is not None:
            rec["csv_slug"] = str(row["slug"])
            rec["description"] = str(row.get("details", ""))[:1200]
            rec["benefits"] = str(row.get("benefits", ""))[:600]
            rec["application"] = str(row.get("application", ""))[:900]
            rec["documents"] = _docs_list(str(row.get("documents", "")))
            rec["tags"] = _tags_list(str(row.get("tags", "")))
        else:
            rec["documents"] = []
            rec["tags"] = []
        rec.pop("csv_slug", None)
        out.append(rec)
    return out


def _docs_list(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(".") if len(p.strip()) > 4]
    return parts[:12]


def _tags_list(raw: str) -> list[str]:
    return [t.strip() for t in raw.split(",") if t.strip()][:10]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", action="store_true", help="push to Firestore too")
    args = parser.parse_args()

    if not CSV_PATH.exists():
        print(f"[!] {CSV_PATH} not found -- will write rules without CSV enrichment")
        lookup = pd.DataFrame({"slug": [], "details": [], "benefits": [], "application": [], "documents": [], "tags": []})
    else:
        lookup = load_csv()

    records = enrich(lookup, CURATED_SCHEMES)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
    print(f"[ok] wrote {len(records)} schemes -> {OUT_JSON}")

    if args.sync:
        from core.db import get_store

        n = get_store().upsert_schemes(records)
        print(f"[ok] pushed {n} schemes to backend '{get_store().backend}'")

    if args.sync or getattr(args, "verify", False):
        from core.rules import evaluate_scheme
        from core.profile_schema import sample_profile

        sample = sample_profile()
        for s in records:
            ev = evaluate_scheme(s, sample)
            flag = "ELIGIBLE " if ev["eligible"] else "not-eligible"
            print(f"  {flag} {s['scheme_id']}  {s['name'][:60]}")


if __name__ == "__main__":
    main()