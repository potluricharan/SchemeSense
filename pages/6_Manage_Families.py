"""Manage the families you have saved — list, edit, delete, and switch to them."""
import uuid
from datetime import datetime

import streamlit as st

from core.db import get_store
from core.profile_schema import FAMILY_FIELDS, MEMBER_FIELDS, blank_member, blank_profile
from core.roles import require_role
from core.ui_helpers import backend_badge, inr

st.set_page_config(page_title="Manage Families · YojanaAI", page_icon="🗂️", layout="wide")

require_role("admin")

MAX_MEMBERS = 15
store = get_store()
families = store.list_profiles()

st.title("🗂️ Manage Families")
st.caption(f"Every family you have run (saved) — pick one to edit, delete, or re-run. Storage: {backend_badge(store)}")


def _render_field(key_prefix, field_key, cfg):
    wkey = f"{key_prefix}_{field_key}"
    kind = cfg["type"]; label = cfg["label"]
    if kind == "text":
        return st.text_input(label, value=cfg["default"], key=wkey, placeholder=cfg.get("placeholder", ""))
    if kind == "number":
        return st.number_input(label, value=float(cfg["default"]), min_value=float(cfg.get("min", 0)),
                               max_value=float(cfg.get("max", 1e9)), step=float(cfg.get("step", 1)), key=wkey)
    if kind == "select":
        return st.selectbox(label, cfg["options"], index=cfg["options"].index(cfg["default"]), key=wkey)
    if kind == "toggle":
        return st.checkbox(label, value=cfg["default"], key=wkey)
    return None


def _clean(profile: dict) -> dict:
    return {k: v for k, v in profile.items() if not str(k).startswith("_")}


if families:
    table = [{
        "Created": datetime.fromtimestamp((f["created_at"] or 0)).strftime("%Y-%m-%d %H:%M"),
        "Family": f["family_name"],
        "State": f["state"], "Area": f["area"],
        "Income": inr(f["annual_income"]), "Members": f["member_count"],
        "ID": f["profile_id"][:14],
    } for f in families]
    st.dataframe(table, hide_index=True, width="stretch")

    st.write("---")
    st.subheader("🗑 Delete a family record")
    family_labels = [f"{f['family_name']} — {f['member_count']} member"
                     f"{'s' if f['member_count'] != 1 else ''}, {f['state'] or 'any'}"
                     f" ({f['profile_id'][:14]}…)" for f in families]
    dcol1, dcol2, dcol3 = st.columns([2, 1, 1])
    with dcol1:
        del_choice = st.selectbox("Pick the family to delete", family_labels, key="quick_del_sel")
    with dcol2:
        del_confirm = st.checkbox("Confirm permanent delete", key="quick_del_confirm")
    with dcol3:
        if st.button("🗑 Delete family", type="secondary", disabled=not del_confirm,
                     width="stretch", key="quick_del_btn"):
            del_fam = families[family_labels.index(del_choice)]
            store.delete_profile(del_fam["profile_id"])
            active = st.session_state.get("profile") or {}
            if active.get("profile_id") == del_fam["profile_id"] or \
               active.get("family_name") == del_fam["family_name"]:
                st.session_state.pop("profile", None)
                st.session_state.pop("profile_saved_id", None)
            st.session_state.pop("quick_del_sel", None)
            st.session_state.pop("quick_del_confirm", None)
            st.success(f"Family '{del_fam['family_name']}' deleted.")
            st.rerun()
    st.write("---")
else:
    st.info("No families saved yet. Register one on **Family Registration** or load the demo family.")

labels = ["➕ New family"] + [
    f"{f['family_name']} ({f['member_count']} member{'s' if f['member_count'] != 1 else ''}, {f['state'] or 'any'})"
    for f in families
]
sel = st.selectbox("Family to view / edit", labels)
tag = "new" if sel.startswith("➕") else f"f_{families[labels.index(sel) - 1]['profile_id']}"

if sel.startswith("➕"):
    current = blank_profile()
    src_members = []
    is_new = True
else:
    fam = families[labels.index(sel) - 1]
    gotten = store.get_profile(fam["profile_id"]) or fam
    current = _clean(gotten)
    src_members = current.get("members", []) or []
    is_new = False

state_key = f"em_members_{tag}"
if state_key not in st.session_state:
    st.session_state[state_key] = [{"id": uuid.uuid4().hex[:8], "data": m} if m else {"id": uuid.uuid4().hex[:8], "data": blank_member()} for m in src_members]
if not st.session_state[state_key]:
    st.session_state[state_key] = [{"id": uuid.uuid4().hex[:8], "data": blank_member()}]

with st.form(f"family_form_{tag}"):
    st.subheader("Family-level details")
    fam_vals = {}
    fam_items = list(FAMILY_FIELDS.items())
    for row_start in range(0, len(fam_items), 3):
        cols = st.columns(3)
        for i, (key, cfg) in enumerate(fam_items[row_start:row_start + 3]):
            st.session_state.setdefault(f"ef_{tag}_{key}", current.get(key, cfg["default"]))
            with cols[i]:
                fam_vals[key] = _render_field(f"ef_{tag}", key, cfg)

    st.write("---")
    st.subheader("Family members (edit / add / remove)")
    remove_target = None
    for i, member in enumerate(st.session_state[state_key]):
        mid = member["id"]
        vals = {}
        with st.expander(f"{i + 1}. {st.session_state.get(f'em_{tag}_{mid}_name') or 'Member'}",
                         expanded=(i == len(st.session_state[state_key]) - 1 and not remove_target)):
            member_items = list(MEMBER_FIELDS.items())
            for row_start in range(0, len(member_items), 3):
                cols = st.columns(3)
                for j, (key, cfg) in enumerate(member_items[row_start:row_start + 3]):
                    st.session_state.setdefault(f"em_{tag}_{mid}_{key}", member["data"].get(key, cfg["default"]))
                    with cols[j]:
                        vals[key] = _render_field(f"em_{tag}_{mid}", key, cfg)
            member["data"] = vals
            if st.form_submit_button(f"🗑 Remove member", width="stretch"):
                remove_target = i

    c_add, c_rem = st.columns(2)
    with c_add:
        add_clicked = st.form_submit_button("➕ Add member", width="stretch")
    with c_rem:
        pass

    st.write("---")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        saved = st.form_submit_button("💾 Save changes", type="primary", width="stretch")
    with c2:
        set_active = st.form_submit_button("Set active family", width="stretch")
    with c3:
        confirm_del = st.checkbox("Confirm delete", value=False)

if remove_target is not None:
    st.session_state[state_key].pop(remove_target)
    st.rerun()

if add_clicked and len(st.session_state[state_key]) < MAX_MEMBERS:
    st.session_state[state_key].append({"id": uuid.uuid4().hex[:8], "data": blank_member()})
    st.rerun()

profile = _clean(blank_profile() if is_new else current)
for k in FAMILY_FIELDS:
    profile[k] = st.session_state.get(f"ef_{tag}_{k}", FAMILY_FIELDS[k]["default"])
profile["members"] = [m["data"] for m in st.session_state[state_key]]

if saved:
    if is_new:
        pid = store.save_profile(profile)
        st.success(f"New family saved (id {pid}).")
    else:
        ok = store.update_profile(fam["profile_id"], profile)
        st.success(f"Family updated (id {fam['profile_id'][:14]}…)." if ok else "Update failed.")
    st.session_state.pop(state_key, None)
    st.rerun()

if set_active:
    if is_new:
        pid = store.save_profile(profile)
    else:
        store.update_profile(fam["profile_id"], profile)
        pid = fam["profile_id"]
    st.session_state["profile"] = profile
    st.session_state["profile_saved_id"] = pid
    st.session_state.pop("opt_result", None)
    st.success(f"Active family set ({pid[:14]}…) — it is now loaded across the app.")

if not is_new and confirm_del:
    if st.button("🗑 Delete this family permanently", type="secondary"):
        store.delete_profile(fam["profile_id"])
        st.session_state.pop(state_key, None)
        st.session_state.pop("profile", None)
        st.success("Family deleted.")
        st.rerun()

if not is_new:
    active = (st.session_state.get("profile") or {}).get("family_name") == current.get("family_name")
    if active:
        st.caption("This is currently the active family loaded in the app.")