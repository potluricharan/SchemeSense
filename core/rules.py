"""Rule engine: evaluates a scheme's eligibility_rules against a family profile.

A scheme is eligible when:
  * every `family`-scope rule passes against the family section, and
  * for every `member_group` there exists at least one member who satisfies ALL
    rules in that group, and
  * every `family_count` rule passes.
"""
from __future__ import annotations

from collections import defaultdict

OPS = ("eq", "ne", "gt", "ge", "lt", "le", "in", "between")


def apply_op(op: str, actual, expected) -> bool:
    if op == "eq":
        return bool(actual == expected)
    if op == "ne":
        return bool(actual != expected)
    if op == "gt":
        return bool(actual is not None and actual > expected)
    if op == "ge":
        return bool(actual is not None and actual >= expected)
    if op == "lt":
        return bool(actual is not None and actual < expected)
    if op == "le":
        return bool(actual is not None and actual <= expected)
    if op == "in":
        return bool(actual in expected)
    if op == "between":
        return bool(actual is not None and expected[0] <= actual < expected[1])
    return False


def _truthy(v) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v > 0
    return bool(str(v).strip())


def rule_key(rule: dict) -> str:
    return f"{rule.get('scope')}:{rule.get('field')}:{rule.get('op')}:{rule.get('value')}"


def check_rule(rule: dict, context: dict) -> bool:
    """Apply a rule to a field-value context."""
    field = rule.get("field", "")
    value = rule.get("value")
    if value is True or value is False or isinstance(value, (int, float)):
        if isinstance(rule.get("value"), bool) and rule["op"] == "eq":
            return _truthy(context.get(field)) == value
    return apply_op(rule.get("op", "eq"), context.get(field), value)


def evaluate_member_rules(grules: list[dict], member: dict) -> list[dict]:
    """Return the subset of rules a member fails."""
    return [r for r in grules if not check_rule(r, member)]


def evaluate_scheme(scheme: dict, profile: dict) -> dict:
    """Full eligibility result for one scheme."""
    profile = profile or {}
    members = profile.get("members", []) or []
    family_ctx = {k: v for k, v in profile.items() if k != "members"}
    
    # Auto-calculate BPL status
    income = float(family_ctx.get("annual_income", 0))
    area = family_ctx.get("area", "rural")
    state = family_ctx.get("state", "Maharashtra")
    
    # Approximate BPL annual income thresholds by state (rural, urban)
    # Based roughly on state-level planning commission guidelines
    bpl_limits = {
        "Andhra Pradesh": (30000, 40000),
        "Bihar": (25000, 32000),
        "Chhattisgarh": (25000, 32000),
        "Gujarat": (32000, 45000),
        "Haryana": (35000, 48000),
        "Karnataka": (31000, 42000),
        "Kerala": (35000, 48000),
        "Madhya Pradesh": (27000, 36000),
        "Maharashtra": (32000, 43000),
        "Odisha": (24000, 31000),
        "Rajasthan": (30000, 40000),
        "Tamil Nadu": (31000, 42000),
        "Uttar Pradesh": (25000, 33000),
        "West Bengal": (26000, 34000),
        "Delhi": (35000, 50000),
    }
    limits = bpl_limits.get(state, (28000, 38000)) # fallback
    threshold = limits[0] if area == "rural" else limits[1]
    
    # Inject computed BPL status so rules engine can check 'bpl' == True
    family_ctx["bpl"] = income <= threshold

    rules = scheme.get("eligibility_rules", [])

    family_failed: list[dict] = []
    count_failed: list[dict] = []
    groups: dict[int, list[dict]] = defaultdict(list)

    for r in rules:
        scope = r.get("scope", "member_group")
        if scope == "family":
            if not check_rule(r, family_ctx):
                family_failed.append(r)
        elif scope == "family_count":
            threshold = r.get("threshold", 1)
            cnt = sum(1 for m in members
                      if check_rule({"op": "ge", "field": r["field"], "value": threshold}, m))
            if not apply_op(r.get("op", "ge"), cnt, r.get("value")):
                count_failed.append(r)
        else:
            groups[r.get("group", 1)].append(r)

    group_summary = {}
    group_ok_indices: dict[int, set] = {}
    for g, grules in groups.items():
        passing_idx = [i for i, m in enumerate(members)
                       if all(check_rule(r, m) for r in grules)]
        group_ok_indices[g] = set(passing_idx)
        group_summary[g] = {
            "passed": bool(passing_idx),
            "members": [m.get("name") or f"Member #{i}" for i, m in enumerate(members) if i in passing_idx],
        }

    if groups:
        eligible_indices = set.intersection(*[group_ok_indices[g] for g in groups]) if len(groups) > 1 else group_ok_indices[next(iter(groups))]
        matched = [m.get("name") or f"Member #{i}" for i, m in enumerate(members) if i in eligible_indices]
    else:
        matched = []

    family_passed = not family_failed
    count_passed = not count_failed
    member_groups_passed = all(gs["passed"] for gs in group_summary.values()) if group_summary else True
    eligible = family_passed and count_passed and member_groups_passed

    all_failed: list[dict] = list(family_failed) + list(count_failed)
    for g, grules in groups.items():
        if not group_ok_indices.get(g):
            all_failed.extend(grules)

    return {
        "scheme_id": scheme.get("scheme_id"),
        "name": scheme.get("name"),
        "category": scheme.get("category", []),
        "level": scheme.get("level", ""),
        "benefit_amount": scheme.get("benefit_amount", 0),
        "benefit_period": scheme.get("benefit_period", "yearly"),
        "benefit_text": scheme.get("benefit_text", ""),
        "eligible": eligible,
        "matched_members": matched,
        "family_passed": family_passed,
        "count_passed": count_passed,
        "member_groups_passed": member_groups_passed,
        "group_summary": group_summary,
        "failed_rules": all_failed,
    }


def evaluate_all(profile: dict, schemes: list[dict]) -> list[dict]:
    return [evaluate_scheme(s, profile) for s in schemes]