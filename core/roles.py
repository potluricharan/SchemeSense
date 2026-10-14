"""Role-based access control for the Streamlit app.

Two roles exist: `family` (households) and `admin` (password-gated). Admin-only
pages (analytics dashboard, family management) call `require_role("admin")`;
family pages call `require_any_role()` so the sign-in screen is the entry point.
"""
from __future__ import annotations

import streamlit as st

FAMILY_ROLE = "family"
ADMIN_ROLE = "admin"


def current_role() -> str | None:
    return st.session_state.get("role")


def is_admin() -> bool:
    return current_role() == ADMIN_ROLE


def is_family() -> bool:
    return current_role() == FAMILY_ROLE


def sign_in_as(role: str) -> None:
    st.session_state["role"] = role


def sign_out() -> None:
    st.session_state.pop("role", None)


def _back_to_sign_in() -> None:
    try:
        st.switch_page("app.py")
    except Exception:
        sign_out()
        st.rerun()


def require_role(required: str) -> bool:
    """Gate a page behind one role (e.g. admin wall). Returns True if allowed."""
    if current_role() == required:
        return True
    st.warning("This section is restricted — sign in with the correct role to view it.")
    if st.button("← Back to sign in", use_container_width=True):
        sign_out()
        _back_to_sign_in()
    st.stop()
    return False


def require_any_role() -> bool:
    """Gate a page behind any signed-in role (no anonymous access)."""
    if current_role():
        return True
    st.warning("Please sign in first — choose **Family Registration** or **Admin**.")
    if st.button("← Go to sign in", use_container_width=True):
        _back_to_sign_in()
    st.stop()
    return False