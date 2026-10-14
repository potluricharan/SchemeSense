"""Regional-language chatbot: RAG over the scheme_rules table.

Phase 1 behaviour:  multilingual-embedding retrieval over scheme_rules + templated
                    answer (works with no API key).
Phase 2 behaviour:  same retrieval fed to LangChain + Groq (full RAG explanation),
                    personalised with the family's optimized result when available.

All I/O here is kept in English; the surrounding page calls
core.translation to wrap the query/answer in the citizen's language.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from core import config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are YojanaAI, an assistant that helps Indian families discover
government welfare schemes (schemes, pensions, scholarships) they qualify for.

Answer ONLY from the scheme rule excerpts provided below and the family details.
Be concise (max ~5 sentences). Structure: what benefit you can get, whether the
family meets the key conditions, and what document/next step is needed.
If the information is not in the excerpts, say you don't have that scheme in the
database. Always name the scheme(s). Reply in plain English.
"""


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer  # heavy import

    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


def _search_text(scheme: dict) -> str:
    parts = [scheme.get("name", "")]
    parts += [str(x) for x in scheme.get("category", [])]
    parts.append(scheme.get("benefit_text", ""))
    parts.append(scheme.get("eligibility_text", ""))
    parts.extend(r.get("explainer", "") for r in scheme.get("eligibility_rules", []))
    parts.append(" ".join(scheme.get("documents", [])))
    parts.append(" ".join(scheme.get("tags", [])))
    return " ".join(p for p in parts if p)


_SCHEME_EMB_CACHE: dict = {"ids": None, "emb": None}


def _scheme_embeddings(schemes: list[dict]):
    ids = tuple(s["scheme_id"] for s in schemes)
    if _SCHEME_EMB_CACHE["ids"] != ids:
        _SCHEME_EMB_CACHE["ids"] = ids
        _SCHEME_EMB_CACHE["emb"] = _embedder().encode([_search_text(s) for s in schemes])
    return _SCHEME_EMB_CACHE["emb"]


def _retrieve(query: str, schemes: list[dict], top_k: int = 4) -> list[dict]:
    if not schemes:
        return []
    try:
        model = _embedder()
        qv = model.encode([query])
        sv = _scheme_embeddings(schemes)
        import numpy as np

        scores = sv @ qv.T
        order = np.argsort(scores[:, 0])[::-1][:top_k]
        out = []
        for idx in order:
            s = schemes[int(idx)]
            out.append({"scheme": s, "score": float(scores[int(idx), 0])})
        return out
    except Exception:
        # keyword fallback (no model weights available)
        return _keyword_retrieve(query, schemes, top_k)


def _keyword_retrieve(query: str, schemes: list[dict], top_k: int = 4) -> list[dict]:
    tokens = {w for w in query.lower().split() if len(w) > 2}
    scored = []
    for s in schemes:
        blob = (_search_text(s) + " " + s.get("name", "")).lower()
        hits = sum(1 for t in tokens if t in blob)
        if hits:
            scored.append({"scheme": s, "score": float(hits), "keyword": True})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def _make_context(query: str, schemes: list[dict], profile: Optional[dict], opt_result: Optional[dict] = None) -> str:
    lines = []
    if profile:
        lines.append(f"FAMILY DETAILS: state={profile.get('state')}, "
                     f"area={profile.get('area')}, annual_income={profile.get('annual_income', 0)}, "
                     f"bpl={profile.get('bpl')}, ration_card={profile.get('ration_card')}, "
                     f"members={len(profile.get('members', []) or [])}")
    if opt_result and opt_result.get("chosen"):
        lines.append("OPTIMIZED PLAN ALREADY CHOSEN FOR THIS FAMILY:")
        for c in opt_result["chosen"]:
            lines.append(f"  - {c['name']} -> \u20b9{c['benefit']}/yr for {c['member_name']}")
    lines.append("RELEVANT SCHEME RULE EXCERPTS:")
    for hit in schemes:
        s = hit["scheme"]
        excerpt = _search_text(s)[:400]
        lines.append(f"[{s.get('scheme_id')}] {s.get('name')} | benefit: {s.get('benefit_text', '')}\n"
                     f"  excerpt: {excerpt}")
    lines.append(f"USER QUESTION: {query}")
    return "\n".join(lines)


def answer(query: str, schemes: list[dict], profile: Optional[dict] = None,
           opt_result: Optional[dict] = None, top_k: int = 4) -> dict:
    hits = _retrieve(query, schemes, top_k)
    if not hits:
        return {"answer": "I don't have that scheme in the current database. "
                          "Try asking about pensions, scholarships, or ration cards.",
                "sources": [], "engine": "retrieval"}

    if config.groq_api_key():
        try:
            return _ask_groq(query, hits, profile, opt_result)
        except Exception as exc:  # pragma: no cover
            log.exception("Groq call failed; using templated answer")
        return _template_answer(query, hits, profile, opt_result, llm_failed=True)
    return _template_answer(query, hits, profile, opt_result)


def _ask_groq(query: str, hits: list[dict], profile, opt_result) -> dict:
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_groq import ChatGroq

    llm = ChatGroq(model=config.groq_model(), api_key=config.groq_api_key(), temperature=0.2)
    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "{context}")])
    chain = prompt | llm
    context = _make_context(query, hits, profile, opt_result)
    resp = chain.invoke({"context": context})
    return {
        "answer": (resp.content or "").strip(),
        "sources": [h["scheme"]["scheme_id"] for h in hits],
        "engine": "langchain+groq",
        "context": context,
    }


def _template_answer(query, hits, profile, opt_result, llm_failed=False) -> dict:
    answers = []
    for h in hits[:3]:
        s = h["scheme"]
        key_rules = "; ".join(
            r.get("explainer", "") for r in s.get("eligibility_rules", [])[:3]
        ) or s.get("eligibility_text", "")
        what_you_get = s.get("benefit_text", "") or s.get("benefits", "see details")
        answers.append(
            f"*{s['name']}*\n- What you get: {what_you_get}\n- Key rule: {key_rules}"
        )
    note = " (LLM unavailable - showing database summary)" if llm_failed else ""
    return {
        "answer": "\n\n".join(answers) + note,
        "sources": [h["scheme"]["scheme_id"] for h in hits],
        "engine": "template" + ("-llmfailed" if llm_failed else ""),
    }