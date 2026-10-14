"""Gap analysis + RAG explanation (Phase 2).

For a scheme already flagged "not eligible" by Phase 1, this module:
  1. re-evaluates the scheme to get the exact failed rules,
  2. compares the OCR-extracted document fields against the expected rule values,
  3. builds a LangChain pipeline that sends the exact rule text + extracted
     fields + the mismatch to the Groq API for a plain-language explanation,
  4. rule-based cross-check: the deterministic mismatch description is validated
     against the LLM output; if the LLM omits the key value/field mention, the
     deterministic text is used (guards against hallucinated explanations).
"""
from __future__ import annotations

import logging
import re

from core import config
from core.rules import apply_op, evaluate_scheme

log = logging.getLogger(__name__)

SYS_PROMPT = """You are YojanaAI's document gap-analysis explainer.
A document was uploaded for a family member applying to a welfare scheme that was
deemed NOT eligible. Below are:
 - the exact scheme eligibility rule(s) that failed,
 - the values extracted from the uploaded document,
 - the explicit mismatch detected.
Explain IN PLAIN LANGUAGE, for a non-technical citizen, (1) exactly which
document/field is the problem, (2) what the scheme requires, (3) what action
fixes it (new certificate, revalidation, apply for specific doc, etc.).
Keep it to ~4 sentences. Do not add rules that are not listed.
"""


def _extracted_to_rule_fields(doc_fields: dict) -> dict:
    """Map OCR-extracted keys onto rule-engine field names."""
    mapping = {
        "annual_income": "annual_income",
        "family_income": "annual_income",
        "income": "annual_income",
        "disability": "disability_pct",
        "disability_pct": "disability_pct",
        "age": "age",
        "dob": "dob",
        "gender": "gender",
        "marital_status": "marital_status",
        "issue_date": "issue_date",
    }
    out = {}
    for k, v in doc_fields.items():
        rule_field = mapping.get(k)
        if rule_field:
            out[rule_field] = v
    return out


def _mismatch_for_rule(rule: dict, extracted: dict) -> str | None:
    """Deterministic cross-check between a failed rule and extracted values."""
    field = rule.get("field")
    if field not in extracted:
        return None
    actual = extracted[field]
    expected = rule.get("value")
    # Value type coercion for numbers in text fields
    try:
        actual_num = float(str(actual).replace(",", ""))
    except (TypeError, ValueError):
        actual_num = None
    if isinstance(expected, (int, float)) and actual_num is not None:
        passes = apply_op(rule.get("op"), actual_num, expected)
    else:
        passes = apply_op(rule.get("op"), actual, expected)
    if passes:
        return None
    expected_txt = expected if isinstance(expected, str) else f"{expected}"
    if isinstance(expected, list):
        expected_txt = " or ".join(str(x) for x in expected)
    return f"Document shows {field} = {actual} but the scheme requires {rule.get('op')} {expected_txt}."


def analyze(scheme: dict, profile: dict, doc_fields: dict, ocr_text: str = "") -> dict:
    failed_rules = []
    try:
        ev = evaluate_scheme(scheme, profile)
        failed_rules = ev.get("failed_rules", [])
    except Exception:
        log.exception("evaluate_scheme failed inside gap analysis")
        failed_rules = scheme.get("eligibility_rules", [])

    field_map = _extracted_to_rule_fields(doc_fields)
    gaps = []
    for rule in failed_rules:
        mismatch = _mismatch_for_rule(rule, field_map)
        gaps.append({
            "rule": rule,
            "explainer": rule.get("explainer", ""),
            "field": rule.get("field"),
            "expected": rule.get("value"),
            "extracted": field_map.get(rule.get("field")),
            "mismatch": mismatch,
        })
    gaps = [g for g in gaps if g["mismatch"] is not None or g["extracted"] is not None]

    deterministic = _build_deterministic(gaps, failed_rules, scheme)

    explanation = deterministic
    engine = "crosscheck"
    if config.groq_api_key() and gaps:
        try:
            llm_out = _ask_llm(scheme, failed_rules, gaps, doc_fields, ocr_text)
            if _crosscheck_llm(llm_out, gaps, scheme):
                explanation = llm_out
                engine = "langchain+groq"
        except Exception as exc:
            log.exception("LLM gap explanation failed; using deterministic text")

    return {
        "scheme_id": scheme.get("scheme_id"),
        "scheme_name": scheme.get("name"),
        "gaps": gaps,
        "explanation": explanation,
        "engine": engine,
        "deterministic": deterministic,
        "fixed": not failed_rules,
    }


def _build_deterministic(gaps, failed_rules, scheme) -> str:
    lines = [f"Your document does not currently satisfy the rules of *{scheme.get('name')}*."]
    if gaps:
        for g in gaps[:4]:
            if g["mismatch"]:
                lines.append(f"- {g['mismatch']}  ({g['explainer']})")
            elif g["extracted"] is None:
                lines.append(f"- {g['explainer']} -- no value for '{g['field']}' found in the document.")
    else:
        seen = set()
        for r in failed_rules[:4]:
            key = r.get("field")
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {r.get('explainer')} (no supporting value found in the document).")
    lines.append("Suggested fix: obtain/renew the missing document, then re-upload it here.")
    return "\n".join(lines)


def _ask_llm(scheme, failed_rules, gaps, doc_fields, ocr_text) -> str:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_groq import ChatGroq

    rule_lines = "\n".join(
        f"- {r.get('explainer', r.get('field'))} [condition: {r.get('field')} {r.get('op')} {r.get('value')}]"
        for r in failed_rules[:8]
    )
    gap_lines = "\n".join(f"- {g['mismatch']}" for g in gaps[:6])
    fields_lines = ", ".join(f"{k}: {v}" for k, v in doc_fields.items() if v not in (None, ""))

    user = (
        f"Scheme: {scheme.get('name')}\n"
        f"Failed eligibility rules:\n{rule_lines}\n\n"
        f"Values extracted from uploaded document:\n{fields_lines}\n\n"
        f"Detected mismatches:\n{gap_lines}\n\n"
        f"Raw OCR text (truncated):\n{ocr_text[:600]}"
    )
    llm = ChatGroq(model=config.groq_model(), api_key=config.groq_api_key(), temperature=0.1)
    prompt = ChatPromptTemplate.from_messages([("system", SYS_PROMPT), ("human", "{user}")])
    resp = (prompt | llm).invoke({"user": user})
    return (resp.content or "").strip()


def _crosscheck_llm(llm_out: str, gaps, scheme) -> bool:
    """Guard against hallucinated explanations: the LLM text must reference at
    least one key token from the deterministic mismatch (field/expected value)."""
    low = llm_out.lower()
    norm = low.replace(",", "").replace("rs.", "").replace("\u20b9", "").replace("inr", "")
    for g in gaps:
        field = g.get("field") or ""
        if field and field.lower() in low:
            return True
    for g in gaps:
        if g.get("extracted") is not None:
            token = str(g["extracted"]).replace(",", "")
            digits = re.sub(r"[^\d]", "", token)  # use all numeric content
            if digits and digits[:5] in norm:
                return True
        expected = g.get("expected")
        if isinstance(expected, (int, float)) and str(expected)[:4] in norm:
            return True
        if isinstance(expected, str) and expected.lower() in low:
            return True
    if scheme.get("name", "").lower() in low:
        return True
    return False