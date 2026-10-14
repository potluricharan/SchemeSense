"""Anonymized statistics layer (writer).

Every completed optimization / gap-analysis run writes an anonymized summary row
(scheme ID, eligible flag, opted flag, region, area, gap category) to a dedicated
`usage_stats` collection. NO personally identifiable fields are stored.
Consumed by Phase 3's dashboard.
"""
from __future__ import annotations

import time
import uuid

from core.db import get_store


def _anonymize(profile: dict) -> dict:
    return {
        "state": profile.get("state", "unknown"),
        "area": profile.get("area", "unknown"),
        "member_count": len(profile.get("members", []) or []),
        "income_band": _income_band(profile.get("annual_income", 0)),
    }


def _income_band(income) -> str:
    try:
        i = float(income)
    except (TypeError, ValueError):
        return "unknown"
    if i <= 60000:
        return "upto_60k"
    if i <= 120000:
        return "60k_to_1.2L"
    if i <= 250000:
        return "1.2L_to_2.5L"
    if i <= 800000:
        return "2.5L_to_8L"
    return "above_8L"


def record_optimization_run(profile: dict, opt_result: dict) -> str:
    anonymized = _anonymize(profile)
    opted = {c["scheme_id"] for c in opt_result.get("chosen", [])}
    rows = []
    for ev in opt_result.get("evals", []):
        rows.append({
            "scheme_id": ev.get("scheme_id"),
            "eligible": bool(ev.get("eligible")),
            "opted": ev.get("scheme_id") in opted,
            "estimated_benefit": ev.get("benefit_amount", 0) if ev.get("eligible") else 0,
        })
    stat = {
        "event": "optimization_run",
        "ts": int(time.time() * 1000),
        "run_id": f"opt_{uuid.uuid4().hex[:10]}",
        **anonymized,
        "schemes": rows,
    }
    return _write(stat)


def record_gap_analysis_run(profile: dict, scheme_id: str, gap_category: str) -> str:
    anonymized = _anonymize(profile)
    stat = {
        "event": "gap_analysis",
        "ts": int(time.time() * 1000),
        "run_id": f"gap_{uuid.uuid4().hex[:10]}",
        **anonymized,
        "scheme_id": scheme_id,
        "gap_category": gap_category,
    }
    return _write(stat)


def _write(stat: dict) -> str:
    get_store().add_usage_stat(stat)
    return stat["run_id"]


def load_stats() -> list[dict]:
    """All anonymized stats, newest first — consumed by the analytics dashboard."""
    return get_store().list_usage_stats()