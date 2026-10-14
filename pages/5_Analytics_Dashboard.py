"""Government-facing analytics dashboard (Phase 3).

Aggregates the anonymized `usage_stats` rows that every optimization run and
gap-analysis run already writes: scheme uptake, eligibility rates and the most
common eligibility-mismatch reasons, per region. No PII is ever displayed.
"""
import random
import time
from collections import Counter
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from core import stats
from core.db import get_store
from core.roles import require_role
from core.ui_helpers import backend_badge

st.set_page_config(page_title="Analytics Dashboard · YojanaAI", page_icon="📈", layout="wide")

require_role("admin")

store = get_store()
schemes = store.list_schemes()
name_of = {s["scheme_id"]: s["name"] for s in schemes}
valid_ids = list(name_of) or ["scheme_a", "scheme_b"]

NOW_MS = int(time.time() * 1000)
DEMO_DAYS = 90
random.seed(2026)


def _demo_stats() -> list[dict]:
    """Synthetic-but-plausible anonymized stats so the dashboard is never empty."""
    states = ["Madhya Pradesh", "Gujarat", "Tamil Nadu", "Bihar", "Rajasthan", "Kerala", "Maharashtra"]
    areas = ["Rural", "Urban", "Semi-urban"]
    bands = ["upto_60k", "60k_to_1.2L", "1.2L_to_2.5L", "2.5L_to_8L", "above_8L"]
    gap_reasons = ["annual_income", "age", "bpl", "ration_card", "gender", "pregnant", "caste"]
    rows: list[dict] = []
    n_opt, n_gap = 260, 120
    for _ in range(n_opt):
        base = NOW_MS - random.randint(0, DEMO_DAYS * 24 * 3_600_000)
        evals = []
        opted_ids = {random.choice(valid_ids) for _ in range(random.randint(0, 3))}
        for sid in valid_ids[:7]:
            eligible = random.random() < 0.3
            evals.append({
                "scheme_id": sid,
                "eligible": eligible,
                "opted": sid in opted_ids,
                "estimated_benefit": (random.randint(600, 24000) if eligible else 0),
            })
        rows.append({
            "event": "optimization_run", "ts": base,
            "run_id": f"opt_demo_{len(rows)}",
            "state": random.choice(states), "area": random.choice(areas),
            "member_count": random.randint(1, 5), "income_band": random.choice(bands),
            "schemes": evals,
        })
    for _ in range(n_gap):
        base = NOW_MS - random.randint(0, DEMO_DAYS * 24 * 3_600_000)
        rows.append({
            "event": "gap_analysis", "ts": base,
            "run_id": f"gap_demo_{len(rows)}",
            "state": random.choice(states), "area": random.choice(areas),
            "member_count": random.randint(1, 5), "income_band": random.choice(bands),
            "scheme_id": random.choice(valid_ids),
            "gap_category": random.choice(gap_reasons),
        })
    return rows


data = stats.load_stats()
using_demo = False
if not data:
    using_demo = True
    data = _demo_stats()

df = pd.DataFrame(data)
df["day"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()

st.title("📈 Government Analytics Dashboard")
st.caption(
    f"Anonymized `usage_stats` aggregation · storage: {backend_badge(store)}"
    + (" · ⚠️ showing **synthetic demo data** (no real runs recorded yet)" if using_demo else "")
)

with st.sidebar:
    st.subheader("Filters")
    all_states = sorted({r.get("state") for r in data if r.get("state")})
    regions = st.multiselect("Region / state", all_states, default=[], key="dash_regions")
    st.caption("Leave empty to include all regions.")

regions = set(regions)
if regions:
    df = df[df["state"].isin(regions)]
if df.empty:
    st.warning("No stats match these filters.")
    st.stop()

opt_df = df[df["event"] == "optimization_run"]
gap_df = df[df["event"] == "gap_analysis"]

# Flatten optimization sub-rows (one per screened scheme) for scheme-level views.
scheme_rows = []
for _, r in opt_df.iterrows():
    for sr in r.get("schemes") or []:
        scheme_rows.append({**r.to_dict(), "scheme_id": sr.get("scheme_id"),
                            "eligible": sr.get("eligible"), "opted": sr.get("opted"),
                            "estimated_benefit": sr.get("estimated_benefit", 0)})
scheme_df = pd.DataFrame(scheme_rows)
del scheme_rows

total_opt = len(opt_df)
total_gap = len(gap_df)
total_opts = int(scheme_df["opted"].sum()) if not scheme_df.empty else 0
avg_benefit = int(scheme_df.loc[scheme_df["opted"], "estimated_benefit"].sum() / total_opt) if total_opt else 0
eligible_rate = (scheme_df["eligible"].mean() * 100) if not scheme_df.empty else 0

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Optimization runs", total_opt)
k2.metric("Gap-analysis runs", total_gap)
k3.metric("Schemes opted", total_opts)
k4.metric("Avg benefit / family", f"₹{avg_benefit:,}" if avg_benefit else "—")
k5.metric("Screening eligible rate", f"{eligible_rate:.0f}%" if scheme_df.shape[0] else "—")

if not opt_df.empty:
    daily = (pd.DataFrame({
        "Optimizations": opt_df.groupby("day").size(),
        "Gap analyses": gap_df.groupby("day").size(),
    }).fillna(0).sort_index())
    import plotly.express as px

    st.subheader("Usage over time")
    fig = px.area(daily, labels={"value": "runs", "day": "date", "variable": "event"})
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02), height=320, margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)

    c_left, c_right = st.columns(2)
    with c_left:
        if not scheme_df.empty:
            uptake = (scheme_df[scheme_df["opted"]]
                      .groupby("scheme_id").size().sort_values(ascending=False).head(10))
            if not uptake.empty:
                st.subheader("Top schemes opted (uptake)")
                fig = px.bar(uptake, orientation="h", labels={"value": "times opted", "scheme_id": ""})
                fig.update_yaxes(categoryorder="total ascending", ticktext=[name_of.get(i, i) for i in uptake.index], tickvals=uptake.index)
                fig.update_layout(height=380, margin=dict(t=10))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No opted schemes yet.")
    with c_right:
        if not gap_df.empty:
            st.subheader("Common eligibility mismatches")
            gaps = gap_df["gap_category"].value_counts().head(8)
            fig = px.bar(gaps, labels={"value": "times mismatched", "gap_category": "document field"})
            fig.update_layout(height=380, margin=dict(t=10))
            st.plotly_chart(fig, use_container_width=True)

    r_left, r_right = st.columns(2)
    with r_left:
        if not opt_df.empty:
            st.subheader("Runs by state")
            fig = px.bar(opt_df["state"].value_counts().head(12),
                         labels={"value": "optimization runs", "state": ""})
            fig.update_layout(height=340, margin=dict(t=10))
            st.plotly_chart(fig, use_container_width=True)
    with r_right:
        if not scheme_df.empty and scheme_df["eligible"].any():
            st.subheader("Eligibility rate by state")
            rate = scheme_df.groupby("state")["eligible"].agg(["mean", "size"]).query("size >= 3")
            if not rate.empty:
                fig = px.bar(rate.reset_index(), x="state", y="mean",
                             labels={"mean": "eligible rate", "state": ""})
                fig.update_yaxes(tickformat=".0%")
                fig.update_layout(height=340, margin=dict(t=10))
                st.plotly_chart(fig, use_container_width=True)

st.subheader("Anonymized sample rows")
view = df[["ts", "event", "state", "area", "member_count", "income_band", "run_id"]].head(50)
view = view.copy()
view["ts"] = pd.to_datetime(view["ts"], unit="ms").dt.strftime("%Y-%m-%d %H:%M")
st.dataframe(view, hide_index=True, width="stretch")

st.caption("No personally identifiable information is stored or shown — only region, area type, "
           "member count, income band, scheme IDs, eligibility flags and gap categories.")