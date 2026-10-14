"""Home page for family users — scheme explorer filtered by their state."""
import streamlit as st

from core import registrations
from core.db import get_store, scheme_states, schemes_for_state
from core.profile_schema import sample_profile
from core.roles import require_any_role
from core.rules import evaluate_all
from core.ui_helpers import inr, period_label

ALL_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir",
    "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Delhi", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Ladakh", "Lakshadweep", "Puducherry",
]

st.set_page_config(page_title="YojanaAI · Home", page_icon="🌾", layout="wide")

require_any_role()

st.title("🌾 YojanaAI")
st.caption("Discover, optimize & understand government welfare schemes for your whole family.")

store = get_store()
schemes = store.list_all_schemes()  # verified rules + full dataset roster
n_verified = len(store.list_schemes())
n_roster = store.count_roster()
profile = st.session_state.get("profile")

eligibility = {}
if profile and n_verified:
    try:
        eligibility = {e["scheme_id"]: e for e in evaluate_all(
            profile, schemes_for_state(profile.get("state"), store.list_schemes()))}
    except Exception:
        eligibility = {}

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Schemes in database", n_verified + n_roster, help=f"{n_verified} verified rules + {n_roster} full-dataset entries (browse/search).")
with c2:
    st.metric("Family profile", "Loaded" if profile else "Not loaded yet")
with c3:
    st.metric(
        "Likely eligible",
        sum(1 for e in eligibility.values() if e["eligible"]) if eligibility else "—",
        help="Rules-engine estimate for the loaded family profile (verified rules only).",
    )

if profile and profile.get("state"):
    st.info(f"📍 Showing schemes for your state **{profile['state']}**. Track your applications in **📋 My Registrations** (see Start here).")

tab_browse, tab_start = st.tabs(["🔍 Explore schemes", "⚡ Start here"])

with tab_browse:
    st.subheader("Scheme explorer")
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    query = f1.text_input("Search", placeholder="e.g. pension, pregnant women, craftsman…")
    cats_all = sorted({c for s in schemes for c in s.get("category", [])})
    with f2:
        levels = st.multiselect("Level", ["Central", "State"], default=[])
    with f3:
        cats = st.multiselect("Category", cats_all, default=[])
    with f4:
        sort_by = st.selectbox("Sort by", ["⭐ Benefit (high → low)", "A → Z"])

    g1, g2 = st.columns([1, 2])
    with g1:
        default_state = (profile or {}).get("state")
        st_sel = st.selectbox(
            "Your state",
            ["All states"] + ALL_STATES,
            index=(ALL_STATES.index(default_state) + 1) if default_state in ALL_STATES else 0,
            help="State-level schemes are filtered to the ones mentioning your state; pick 'All states' to see everything.",
        )
    with g2:
        include_central = st.checkbox("Include Central schemes (apply nationwide)", value=True)

    q = (query or "").strip().lower()
    rows = []
    for s in schemes:
        if s.get("level") == "Central" and not include_central:
            continue
        if st_sel != "All states" and s.get("level") != "Central":
            if st_sel not in scheme_states(s):
                continue
        if levels and s.get("level") not in levels:
            continue
        if cats and not set(cats).intersection(s.get("category", [])):
            continue
        hay = " ".join([s.get("name", ""), str(s.get("tags", [])), s.get("description", ""), str(s.get("category", []))]).lower()
        if q and q not in hay:
            continue
        rows.append(s)
    rows.sort(key=lambda s: (-(s.get("benefit_amount") or 0)) if "Benefit" in sort_by else s.get("name", ""))
    st.caption(f"**{len(rows)}** scheme(s) — state: `{st_sel}` · Central included: `{'yes' if include_central else 'no'}`")

    if not rows:
        st.info("No schemes match those filters.")
    else:
        st.caption("Click any scheme below to view its details (showing up to 150 matches).")
        for s in rows[:150]:
            verified = s.get("rules_verified", True if s.get("benefit_amount") else False) or bool(s.get("eligibility_rules"))
            if verified:
                ev = eligibility.get(s.get("scheme_id"))
                badge = "✅ Eligible" if ev and ev["eligible"] else "🚫 Not eligible" if ev and not ev["eligible"] else "◻️ No profile"
            else:
                badge = "📚 Dataset entry"
            
            st_names = sorted(scheme_states(s))
            applies_to = ", ".join(st_names) if st_names else ("🌏 All India" if s.get("level") == "Central" else "n/a")
            
            with st.expander(f"{badge}  |  {s['name']}  |  {s.get('level', '—')}  |  {', '.join(s.get('category', []))}"):
                meta = st.columns(3)
                if verified:
                    meta[0].markdown(f"**Benefit:** {inr(s.get('benefit_amount', 0))} / {period_label(s.get('benefit_period', 'yearly'))}")
                    meta[1].markdown(f"**Level:** {s.get('level')}  ·  **Category:** {', '.join(s.get('category', []))}")
                    ev = eligibility.get(s.get("scheme_id"))
                    if ev and ev["matched_members"]:
                        meta[2].markdown(f"**Matched member(s):** {', '.join(ev['matched_members'])}")
                    elif ev and ev["failed_rules"]:
                        meta[2].markdown("**Missing:** not all rules pass")
                else:
                    meta[0].markdown(f"**Level:** {s.get('level')}  ·  **Category:** {', '.join(s.get('category', []))}")
                    meta[2].markdown("**Dataset:** `updated_data.csv` — full-text entry, eligibility not machine-checked")
                    
                st.markdown(f"**Applies to:** {applies_to}")
                
                if verified and s.get("benefit_text"):
                    st.write(s.get("benefit_text"))
                if s.get("benefits"):
                    st.markdown("**What you get**")
                    st.write(s["benefits"])
                if s.get("eligibility_text"):
                    st.markdown("**Eligibility**")
                    st.write(s["eligibility_text"])
                if s.get("description"):
                    st.markdown("**About**")
                    st.write(s["description"])
                if s.get("documents"):
                    st.markdown("**Documents needed:** " + ", ".join(s["documents"]))
                if s.get("application"):
                    st.markdown("**How to apply**")
                    st.write(s["application"])
                        
                track_key = f"track_{s['scheme_id']}"
                if st.button("➕ Track this scheme in My Registrations", key=track_key, type="primary"):
                    pid = st.session_state.get("profile_saved_id") or "local"
                    registrations.add_registration(pid, s["scheme_id"], s["name"])
                    st.success(f"Added **{s['name']}** to My Registrations.")
                    try:
                        st.switch_page("pages/7_My_Registrations.py")
                    except Exception:
                        st.rerun()

        if len(rows) > 150:
            st.info(f"...and {len(rows) - 150} more schemes. Use the search filters above to narrow down.")

with tab_start:
    st.subheader("Your workspace")
    a1, a2, a3, a4, a5 = st.columns(5)
    with a1:
        if st.button("🏠 State schemes", use_container_width=True, type="primary"):
            st.switch_page("pages/0_Home.py")
    with a2:
        if st.button("🧑‍🤝‍🧑 Register family", use_container_width=True):
            st.switch_page("pages/1_Family_Registration.py")
    with a3:
        if st.button("📋 My registrations", use_container_width=True):
            st.switch_page("pages/7_My_Registrations.py")
    with a4:
        if st.button("📊 Run optimizer", use_container_width=True):
            st.switch_page("pages/2_Optimizer_Results.py")
    with a5:
        if st.button("💬 Regional chat", use_container_width=True):
            st.switch_page("pages/3_Regional_Chat.py")

    st.divider()
    if not profile:
        if st.button("🧪 Load the demo family (fast path)", width="stretch"):
            demo = sample_profile()
            st.session_state["profile"] = demo
            st.session_state["profile_saved_id"] = store.save_profile(demo)
            st.success("Demo family loaded & saved to " + store.backend + ".")
            st.rerun()
        st.info("Load a family to unlock eligibility badges, the optimizer, and smarter chat answers.")
    else:
        fam = profile.get("family_name") or "your family"
        n = len(profile.get("members", []) or [])
        wan = [e["name"] for e in eligibility.values() if e["eligible"]]
        st.success(f"**{fam}** is loaded ({n} members).")
        if wan:
            st.markdown("**Already eligible for:** " + ", ".join(f"`{w}`" for w in wan[:6]))
        st.markdown("Next: hit **📊 Run optimizer** to find the best combination of benefits, "
                    "then **📋 My registrations** to start applying.")