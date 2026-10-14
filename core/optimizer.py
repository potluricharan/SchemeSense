"""Family-level optimization engine.

Two stages:
  1. Rule-based individual screening (core.rules.evaluate_scheme) checks every
     scheme in the scheme_rules table against the family profile and returns the
     eligible scheme list per member.
  2. An OR-Tools CP-SAT model picks the benefit-maximizing combination with:
       - binary decision variables over (member, scheme),
       - mutual-exclusivity constraints (e.g. only one pension per member),
       - per-member scheme caps and an optional total benefit cap.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from ortools.sat.python import cp_model  # type: ignore

from core.rules import evaluate_scheme

log = logging.getLogger(__name__)


def annualize(scheme: dict) -> int:
    """Convert a scheme's benefit to an indicative annual value (₹)."""
    return int(scheme.get("benefit_amount", 0) or 0)


def optimize_schemes(
    schemes: list[dict],
    profile: dict,
    max_schemes_per_member: int = 4,
    benefit_cap: int | None = None,
) -> dict:
    profile = profile or {}
    members = profile.get("members", []) or []
    name_of = {idx: (m.get("name") or f"Member #{idx}") for idx, m in enumerate(members)}

    evals: list[dict] = []
    candidates: list[tuple[dict, int]] = []  # (scheme, member_index)
    for s in schemes:
        ev = evaluate_scheme(s, profile)
        evals.append(ev)
        if not ev["eligible"]:
            continue
        matched = ev["matched_members"]
        if matched:
            for idx, m in enumerate(members):
                if m.get("name") in matched:
                    candidates.append((s, idx))
        else:
            candidates.append((s, 0))  # family-level scheme -> attribute to head

    if not candidates:
        return {
            "OK": True,
            "status": "no candidates",
            "chosen": [],
            "per_member": {},
            "total_benefit": 0,
            "evals": evals,
            "solver_status": "NO_CANDIDATES",
            "languages": {},
        }

    model = cp_model.CpModel()
    x: dict[tuple[str, int], cp_model.BoolVar] = {}
    benefits: dict[tuple[str, int], int] = {}
    for s, midx in candidates:
        key = (s["scheme_id"], midx)
        x[key] = model.NewBoolVar(f"x_{s['scheme_id']}_{midx}")
        benefits[key] = annualize(s)

    model.Maximize(sum(x[k] * benefits[k] for k in x))

    # Mutual exclusivity: at most one scheme of the same exclusive_group per member
    group_vars: dict[tuple[int, str], list] = defaultdict(list)
    for (sid, midx) in x:
        g = next((s.get("exclusive_group") for s, _ in candidates
                  if s["scheme_id"] == sid), None)
        if g and g != "none":
            group_vars[(midx, g)].append(x[(sid, midx)])
    for key, vars_ in group_vars.items():
        model.Add(sum(vars_) <= 1)

    # Per-member cap
    member_vars: dict[int, list] = defaultdict(list)
    for (sid, midx) in x:
        member_vars[midx].append(x[(sid, midx)])
    for midx, vars_ in member_vars.items():
        model.Add(sum(vars_) <= max_schemes_per_member)

    if benefit_cap:
        model.Add(sum(x[k] * benefits[k] for k in x) <= benefit_cap)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 20.0
    status = solver.Solve(model)

    chosen: list[dict] = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (sid, midx) in x:
            if solver.Value(x[(sid, midx)]) == 1:
                s = next(s for s, _ in candidates if s["scheme_id"] == sid)
                chosen.append({
                    "scheme_id": s["scheme_id"],
                    "name": s["name"],
                    "member_index": midx,
                    "member_name": name_of[midx],
                    "benefit": benefits[(sid, midx)],
                    "benefit_period": s.get("benefit_period", "yearly"),
                    "benefit_text": s.get("benefit_text", ""),
                    "level": s.get("level", ""),
                    "category": s.get("category", []),
                })

    chosen.sort(key=lambda c: c["member_index"])
    total = sum(c["benefit"] for c in chosen)
    per_member: dict[str, list[dict]] = defaultdict(list)
    for c in chosen:
        per_member[c["member_name"]].append(c)

    return {
        "OK": True,
        "status": "solved",
        "chosen": chosen,
        "per_member": dict(per_member),
        "total_benefit": total,
        "evals": evals,
        "solver_status": solver.StatusName(status),
        "annualized": True,
    }