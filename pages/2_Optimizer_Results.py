import streamlit as st

from core import registrations, stats
from core.db import get_store, schemes_for_state
from core.optimizer import optimize_schemes
from core.roles import require_any_role
from core.ui_helpers import inr, period_label

st.set_page_config(page_title="Optimizer Results · YojanaAI", page_icon="📊", layout="wide")
require_any_role()
st.title("2 · Family-Level Optimization")
st.caption("Rule-based screening + OR-Tools CP-SAT benefit maximization")

profile = st.session_state.get("profile")

if profile is None:
    st.warning("No family profile loaded yet. Register one on the **Family Registration** page "
               "or load the demo family from the **Home** page.")
    if st.button("Open Family Registration"):
        st.switch_page("pages/1_Family_Registration.py")
    st.stop()

schemes = schemes_for_state(profile.get("state"), get_store().list_schemes())

if not schemes:
    st.warning("No verified schemes match your state yet. Only Central + your state's schemes are considered; "
               "try a different state or use the Home explorer for the full dataset.")
    st.stop()

just_saved = st.session_state.pop("just_saved_family", None)
if just_saved:
    st.success(f"Family profile saved (id {st.session_state.get('profile_saved_id', '')}). Here are the optimized results.")

st.subheader(f"Family: {profile.get('family_name', 'Unnamed')}")
m0, m1, m2 = st.columns(3)
with m0:
    st.metric("Members", len(profile.get("members", [])))
with m1:
    st.metric("Annual income", inr(profile.get("annual_income", 0)))
with m2:
    st.metric("State / Area", f"{profile.get('state', '-')} · {profile.get('area', '-')}")

res = st.session_state.get("opt_result")
auto_ran = False
if res is None and profile:
    with st.spinner("Auto-optimizing: screening schemes + solving CP-SAT model..."):
        res = optimize_schemes(schemes, profile)
    st.session_state["opt_result"] = res
    stats.record_optimization_run(profile, res)
    auto_ran = True

if st.button("🚀 Re-run optimization", type="primary", width="stretch"):
    with st.spinner("Screening schemes + solving CP-SAT model..."):
        res = optimize_schemes(schemes, profile)
    st.session_state["opt_result"] = res
    stats.record_optimization_run(profile, res)

res = st.session_state.get("opt_result")
if res is None:
    st.info("Run the optimization to see the benefit-maximizing scheme combination.")
    st.stop()

st.write("---")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Optimized total benefit", inr(res["total_benefit"]), help="Annualised estimate")
with c2:
    st.metric("Schemes assigned", len(res["chosen"]))
with c3:
    st.metric("CP-SAT status", res["solver_status"])

st.subheader("Assigned scheme combination")
if res["chosen"]:
    df_chosen = [
        {
            "Member": c["member_name"],
            "Scheme": c["name"],
            "Level": c["level"],
            "Category": ", ".join(c["category"][:2]),
            "Benefit": c["benefit"],
            "Benefit_Formatted": inr(c["benefit"]),
            "Period": c["benefit_period"],
        }
        for c in res["chosen"]
    ]
    st.dataframe(
        [
            {
                "Member": d["Member"],
                "Scheme": d["Scheme"],
                "Level": d["Level"],
                "Category": d["Category"],
                "Benefit": d["Benefit_Formatted"],
                "Period": d["Period"],
            } for d in df_chosen
        ],
        width="stretch",
        hide_index=True,
    )
    
    import plotly.express as px
    import pandas as pd
    
    if any(d["Benefit"] > 0 for d in df_chosen):
        st.subheader("Benefit Breakdown")
        pie_df = pd.DataFrame(df_chosen)
        fig = px.pie(pie_df, values='Benefit', names='Scheme', hole=0.4)
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("**Register the schemes you want to apply for — each saved scheme lands in 📋 My Registrations:**")
    pid = st.session_state.get("profile_saved_id") or "local"
    for c in res["chosen"]:
        cols = st.columns([4, 1])
        cols[0].markdown(
            f"**{c['name']}** — {c['level']} · {', '.join(c['category'][:2])} · "
            f"{inr(c['benefit'])}{period_label(c['benefit_period'])} · for *{c['member_name']}*"
        )
        if cols[1].button("➕ Register", key=f"reg_{c['scheme_id']}_{c['member_name']}", type="primary", width="stretch"):
            registrations.add_registration(pid, c["scheme_id"], c["name"])
            st.session_state["just_registered_name"] = c["name"]
            st.session_state["just_registered_id"] = c["scheme_id"]
            st.success(f"Added **{c['name']}** to My Registrations.")
            try:
                st.switch_page("pages/7_My_Registrations.py")
            except Exception:  # AppTest cannot follow page switches
                st.rerun()
else:
    st.warning("No eligible schemes found for this family. Try adjusting income/BPL details or loading the demo family.")

st.write("---")
st.subheader("Why each member is / isn't eligible")
for m in profile.get("members", []):
    mname = m.get("name") or "Unnamed"
    with st.expander(f"Member: {mname}", expanded=False):
        matched = [c for c in res["chosen"] if c["member_name"] == mname]
        if matched:
            st.markdown("**Assigned:** " + ", ".join(f"*{c['name']}* ({inr(c['benefit'])}{period_label(c['benefit_period'])})" for c in matched))
        st.markdown("**Screened schemes:**")
        for ev in res["evals"]:
            if not ev["matched_members"] or mname not in ev["matched_members"]:
                continue
            mark = "✅ eligible" if ev["eligible"] else "N/A"
            st.markdown(f"- {ev['name']} — {mark}")
        st.markdown("**Schemes this member does not qualify for (gap-analysis candidates):**")
        for ev in res["evals"]:
            if ev["eligible"] or (ev["matched_members"] and mname not in ev["matched_members"]):
                continue
            failed = ev["failed_rules"]
            with st.popover(f"{ev['name']} — why not?"):
                for r in failed[:4]:
                    st.markdown(f"- {r.get('explainer', r.get('field'))}")
                if st.button("🔍 Check my document for this scheme", key=f"gap_{ev['scheme_id']}_{mname}", type="primary"):
                    st.session_state["pending_scheme"] = ev["scheme_id"]
                    st.session_state["pending_member"] = mname
                    st.switch_page("pages/4_Document_Analysis.py")