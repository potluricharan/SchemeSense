"""Family registration tracker — the separate section for scheme applications."""
import time

import streamlit as st

from core import registrations
from core.db import get_store, schemes_for_state
from core.roles import require_any_role
from core.ui_helpers import backend_badge

st.set_page_config(page_title="My Registrations · YojanaAI", page_icon="📋", layout="wide")

require_any_role()

store = get_store()
profile = st.session_state.get("profile")
pid = st.session_state.get("profile_saved_id")

st.title("📋 My Registrations")
st.caption(f"Track every scheme you are applying for — own-state and Central. Storage: {backend_badge(store)}")

if not profile:
    st.info("Load a family profile first (**Home → Start here → Register family / demo family**), "
            "then come back here to track its applications.")
    st.stop()

just_name = st.session_state.pop("just_registered_name", None)
just_id = st.session_state.pop("just_registered_id", None)
if just_name:
    st.success(f"✅ **{just_name}** was added to your registrations from the Optimizer results — set its status below.")

schemes = {s["scheme_id"]: s for s in store.list_all_schemes()}

with st.expander("➕ Track a new scheme", expanded=True):
    state = (profile or {}).get("state")
    cands = schemes_for_state(state, list(schemes.values()))
    cands.sort(key=lambda s: (not s.get("rules_verified"), s["name"]))
    labels = {}
    for s in cands:
        labels.setdefault(s["name"], s["scheme_id"])
    if not labels:
        st.caption("No schemes matched. Save a family profile first so we know your state.")
    else:
        pick = st.selectbox("Scheme", list(labels), index=0)
        note = st.text_area("Note (optional)", placeholder="e.g. applying with family ration card", height=70)
        if st.button("➕ Add to my registrations", type="primary"):
            sid = labels[pick]
            registrations.add_registration(pid or "local", sid, schemes[sid]["name"], note)
            st.success(f"Added **{schemes[sid]['name']}** — update its status below.")
            st.rerun()

rows = registrations.list_registrations(profile_id=pid)
st.write("---")
st.subheader(f"Your registrations ({len(rows)})")
if not rows:
    st.info("Nothing tracked yet — add a scheme above (or tap **➕ Track this scheme** on the Home page).")

for r in rows:
    scheme = schemes.get(r.get("scheme_id")) or {"name": r.get("scheme_name", "Scheme")}
    current_status = r.get("status") or "Not started"
    default_open = r.get("scheme_id") == just_id
    with st.expander(f"{scheme['name']} — *{current_status}*", expanded=default_open):
        st.caption(f"Started: {time.strftime('%Y-%m-%d %H:%M', time.localtime(r.get('ts') or 0))}")
        if scheme.get("level") or scheme.get("category"):
            st.caption(f"Level: {scheme.get('level', '—')} · Category: {', '.join(scheme.get('category', [])[:3]) or '—'}")
        s_key = f"st_{r['id']}"
        n_key = f"nt_{r['id']}"
        new_status = st.selectbox("Status", registrations.STATUSES,
                                  index=registrations.STATUSES.index(current_status)
                                  if current_status in registrations.STATUSES else 0,
                                  key=s_key)
        new_note = st.text_area("Note", value=r.get("note", ""), height=70, key=n_key)
        c1, c2, c3 = st.columns([3, 3, 4])
        with c1:
            if st.button("💾 Save status", key=f"sv_{r['id']}"):
                registrations.update_registration(r["id"], new_status, new_note)
                st.success("Saved.")
                st.rerun()
        with c2:
            if st.button("🗑 Remove", key=f"rm_{r['id']}"):
                registrations.delete_registration(r["id"])
                st.rerun()
        with c3:
            if scheme.get("application"):
                with st.expander("Apply here"):
                    st.write(scheme["application"])