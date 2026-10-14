"""YojanaAI backend service (Phase 3 orchestration).

A thin FastAPI layer exposing the same modules the Streamlit app uses directly,
so the stack can be containerized as separate web + API services per the spec.

Run:  uvicorn api:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from core import stats
from core.db import get_store
from core.optimizer import optimize_schemes

app = FastAPI(title="YojanaAI API", version="3.0.0")


class ProfilePayload(BaseModel):
    profile: dict


@app.get("/health")
def health():
    store = get_store()
    return {
        "status": "ok",
        "backend": store.backend,
        "health": store.health,
        "verified_schemes": len(store.list_schemes()),
        "dataset_schemes": store.count_roster(),
    }


@app.get("/schemes")
def schemes():
    return get_store().list_schemes()


@app.post("/optimize")
def optimize(payload: ProfilePayload) -> dict:
    result = optimize_schemes(get_store().list_schemes(), payload.profile)
    stats.record_optimization_run(payload.profile, result)
    return result


@app.get("/stats")
def analytics(limit: int = 2000):
    """Anonymized usage aggregates for external dashboards."""
    rows = stats.load_stats()[:limit]
    from collections import Counter

    opts = [r for r in rows if r["event"] == "optimization_run"]
    gaps = [r for r in rows if r["event"] == "gap_analysis"]
    uptake = Counter()
    for r in opts:
        for s in r.get("schemes") or []:
            if s.get("opted"):
                uptake[s["scheme_id"]] += 1
    by_state = Counter(r.get("state", "unknown") for r in rows)
    return {
        "total_rows": len(rows),
        "optimization_runs": len(opts),
        "gap_runs": len(gaps),
        "top_uptake": uptake.most_common(10),
        "gap_categories": Counter(g["gap_category"] for g in gaps).most_common(10),
        "runs_by_state": dict(by_state.most_common(20)),
    }