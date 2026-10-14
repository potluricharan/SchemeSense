import uuid

import streamlit as st

from core.db import get_store
from core.profile_schema import FAMILY_FIELDS, MEMBER_FIELDS, blank_member, blank_profile, sample_profile
from core.roles import require_any_role
from core.ui_helpers import backend_badge

st.set_page_config(page_title="Family Registration · YojanaAI", page_icon="🧑‍🤝‍🧑", layout="wide")
require_any_role()

MAX_MEMBERS = 15


def _render_field(key_prefix, field_key, cfg):
    kind = cfg["type"]
    label = cfg["label"]
    wkey = f"{key_prefix}_{field_key}"
    if kind == "text":
        kwargs = {"max_chars": 10} if field_key == "mobile" else {}
        return st.text_input(label, value=cfg["default"], key=wkey, placeholder=cfg.get("placeholder", ""), **kwargs)
    if kind == "number":
        return st.number_input(label, value=float(cfg["default"]),
                               min_value=float(cfg.get("min", 0)), max_value=float(cfg.get("max", 1e9)),
                               step=float(cfg.get("step", 1)), key=wkey)
    if kind == "select":
        return st.selectbox(label, cfg["options"], index=cfg["options"].index(cfg["default"]), key=wkey)
    if kind == "toggle":
        return st.checkbox(label, value=cfg["default"], key=wkey)
    return None


def _seed_member_keys(member_entry):
    mid = member_entry["id"]
    for key, cfg in MEMBER_FIELDS.items():
        st.session_state[f"m{mid}_{key}"] = member_entry["data"].get(key, cfg["default"])


def _init_members():
    if "family_members" not in st.session_state:
        existing = (st.session_state.get("profile") or {}).get("members") or []
        st.session_state["family_members"] = [
            {"id": uuid.uuid4().hex[:8], "data": dict(m) if m else blank_member()} for m in existing
        ]
    if not st.session_state["family_members"]:
        st.session_state["family_members"] = [{"id": uuid.uuid4().hex[:8], "data": blank_member()}]
    for member_entry in st.session_state["family_members"]:
        _seed_member_keys(member_entry)


def _profile_seeded():
    st.session_state.setdefault("profile_seeded_from_form", False)
    p = st.session_state.get("profile")
    if p and not st.session_state["profile_seeded_from_form"] and "family_members" not in st.session_state:
        for k, v in p.items():
            if k != "members":
                st.session_state[f"f_{k}"] = v
    if "family_members" not in st.session_state:
        _init_members()


st.title("1 · Family Registration")
st.caption(f"Storage: {backend_badge(get_store())} — add as many family members as you need.")

_profile_seeded()

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    if st.button("➕ Add family member", type="primary", use_container_width=True):
        if len(st.session_state["family_members"]) < MAX_MEMBERS:
            st.session_state["family_members"].append({"id": uuid.uuid4().hex[:8], "data": blank_member()})
            st.rerun()
        else:
            st.error(f"Maximum {MAX_MEMBERS} members supported in this demo.")
with c2:
    if st.button("🧪 Load demo family (sample)", use_container_width=True):
        demo = sample_profile()
        st.session_state["profile"] = demo
        st.session_state["profile_seeded_from_form"] = True
        st.session_state["family_members"] = [
            {"id": uuid.uuid4().hex[:8], "data": dict(m)} for m in demo["members"]
        ]
        for k, v in demo.items():
            if k != "members":
                st.session_state[f"f_{k}"] = v
        for member_entry in st.session_state["family_members"]:
            _seed_member_keys(member_entry)
        get_store().save_profile(demo)
        st.success("Demo family loaded — review the members below, then Save.")
        st.rerun()
with c3:
    st.caption(f"**{len(st.session_state['family_members'])}** member(s) in the family.")

st.write("---")
st.subheader("Family-level details")
fcols = st.columns(3)
fam_vals = {}
for i, (key, cfg) in enumerate(FAMILY_FIELDS.items()):
    with fcols[i % 3]:
        fam_vals[key] = _render_field("f", key, cfg)

st.write("---")
st.subheader("Family members")

for i, member in enumerate(st.session_state["family_members"]):
    mid = member["id"]
    name_val = st.session_state.get(f"m{mid}_name") or f"Member {i + 1}"
    with st.expander(f"{i + 1}. {name_val}", expanded=(i == len(st.session_state["family_members"]) - 1)):
        cols = st.columns(3)
        vals = {}
        for j, (key, cfg) in enumerate(MEMBER_FIELDS.items()):
            with cols[j % 3]:
                vals[key] = _render_field(f"m{mid}", key, cfg)
        member["data"] = vals
        rm = st.columns([9, 1])
        with rm[1]:
            if st.button("🗑 Remove", key=f"rm_{mid}", type="secondary"):
                st.session_state["family_members"].pop(i)
                st.rerun()

st.write("---")
if st.button("💾 Save family profile", type="primary", use_container_width=True):
    mobile_val = str(st.session_state.get("f_mobile", "")).strip()
    if not mobile_val.isdigit() or len(mobile_val) != 10:
        st.error("Registration failed: Mobile number must be exactly 10 digits and contain only numbers.")
        st.stop()
        
    profile = blank_profile()
    for k in FAMILY_FIELDS:
        profile[k] = st.session_state.get(f"f_{k}", FAMILY_FIELDS[k]["default"])
    members = [m["data"] for m in st.session_state["family_members"]]
    profile["members"] = members
    st.session_state["profile"] = profile
    st.session_state["profile_seeded_from_form"] = True
    st.session_state["just_saved_family"] = True
    st.session_state.pop("opt_result", None)  # make the optimizer re-run for this family
    pid = get_store().save_profile(profile)
    st.session_state["profile_saved_id"] = pid
    st.switch_page("pages/2_Optimizer_Results.py")