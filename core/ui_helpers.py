"""Small UI helpers shared by the Streamlit pages."""
from __future__ import annotations


def inr(amount) -> str:
    """Format a number like 12000 -> '₹12,000'."""
    try:
        v = float(amount or 0)
    except (TypeError, ValueError):
        v = 0
    neg = "-" if v < 0 else ""
    s = f"{abs(v):,.0f}"
    return f"{neg}\u20b9{s}"


def period_label(period: str) -> str:
    return {
        "yearly": "/ year",
        "monthly": "/ month",
        "one_time": " (one-time)",
        "loan": " (loan)",
    }.get(period, "")


def humanize_bool(v) -> str:
    return "Yes" if v else "No"


def member_summary(m: dict) -> str:
    parts = [str(m.get("name") or "Unnamed")]
    if m.get("age"):
        parts.append(f"{m['age']} y")
    if m.get("gender") and m["gender"] != "male":
        parts.append(m["gender"])
    return " · ".join(parts)


def backend_badge(store) -> str:
    if store.backend == "firestore":
        return ":green[Firestore connected]"
    if store.health.startswith("firestore:error"):
        return f":orange[Local storage (Firestore pending: {store.health.split(':')[-1]})]"
    return ":blue[Local JSON storage]"