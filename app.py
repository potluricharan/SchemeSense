"""Sign-in gate for YojanaAI — two roles, nothing else shown.

  * Family -> the family workspace only (their state's schemes, registration,
              optimizer, chat, document analysis, application tracker).
  * Admin  -> configured password then ONLY the admin pages (analytics dashboard,
              manage families).

Pages are built per-role with `st.navigation`, so the sidebar of each role shows
its own pages and nothing else; no "restricted" pages ever appear for the other
role.
"""
import streamlit as st

from core.config import get as get_config
from core.roles import current_role, sign_in_as, sign_out

st.set_page_config(page_title="YojanaAI", page_icon="🌾", layout="wide")


def login_page() -> None:
    st.html(
        """
        <style>
        /* ---- page canvas -------------------------------------------------- */
        [data-testid="stApp"] { background: #09090b; }
        [data-testid="stSidebar"] { display: none; }
        #MainMenu, footer { visibility: hidden; }
        [data-testid="stMainBlockContainer"], .block-container { 
            max-width: 860px; padding-top: 4rem; padding-bottom: 3rem; 
        }

        /* ---- brand header ------------------------------------------------ */
        .brand { text-align: center; margin-bottom: 2.5rem; }
        .brand .logo {
          width: 80px; height: 80px; margin: 0 auto 1.2rem; border-radius: 24px;
          display: flex; align-items: center; justify-content: center; font-size: 42px;
          background: linear-gradient(135deg, #fde68a 0%, #f59e0b 100%);
          border: 2px solid #fbbf24; box-shadow: 0 12px 32px rgba(245, 158, 11, 0.2);
        }
        .brand h1 { font-size: 2.6rem; margin: 0; color: #ffffff; letter-spacing: -0.03em; font-weight: 800; }
        .brand .sub { color: #a1a1aa; margin: 0.6rem 0 0; font-size: 1.1rem; font-weight: 400; line-height: 1.5; }

        /* ---- container & tabs -------------------------------------------------- */
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: #18181b;
            border: 1px solid #27272a;
            border-radius: 24px;
            box-shadow: 0 24px 48px rgba(0,0,0, 0.5);
            padding: 2rem 2rem;
        }

        [data-testid="stTabs"] {
            padding: 0 1rem;
        }
        [data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 8px; background: #27272a; padding: 6px;
            border-radius: 16px; margin-bottom: 1rem;
        }
        [data-testid="stTabs"] [data-baseweb="tab"] {
            height: 48px; border-radius: 12px; padding: 0 24px;
            background: transparent; color: #a1a1aa; font-weight: 600; border-bottom: none;
            transition: all 0.2s ease;
        }
        [data-testid="stTabs"] [data-baseweb="tab"]:hover { background: #3f3f46; color: #f4f4f5; }
        [data-testid="stTabs"] [aria-selected="true"] {
            background: #3f3f46; color: #fbbf24;
            box-shadow: 0 4px 12px rgba(0,0,0, 0.2);
        }
        [data-testid="stTabs"] [data-baseweb="tab-highlight"],
        [data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }

        .panel-desc { color: #d4d4d8; font-size: 1.05rem; line-height: 1.6; margin: 0.5rem 0 1.5rem; text-align: center; }
        
        .chips { margin: 1.5rem 0; display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
        .chip {
          background: #27272a; color: #f4f4f5;
          border: 1px solid #3f3f46; border-radius: 8px; padding: 0.4rem 0.8rem;
          font-size: 0.85rem; font-weight: 500;
        }

        /* ---- inputs ---------------------------------------------------------- */
        [data-testid="stTextInput"] label p { color: #d4d4d8; font-weight: 500; }
        [data-testid="stTextInput"] input {
          border-radius: 12px; border: 1px solid #3f3f46;
          background: #09090b; padding: 0.75rem 1rem; font-size: 1rem;
          color: #f4f4f5; -webkit-text-fill-color: #f4f4f5;
        }
        [data-testid="stTextInput"] input:focus {
          border-color: #fbbf24; box-shadow: 0 0 0 2px rgba(251, 191, 36, 0.2);
        }

        /* ---- cta buttons ----------------------------------------- */
        [data-testid="stBaseButton-primary"] {
          height: 54px; border-radius: 14px; border: none; margin-top: 1rem;
          font-weight: 600; font-size: 1.1rem;
          background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
          box-shadow: 0 8px 20px rgba(217, 119, 6, 0.25);
          color: #ffffff; transition: all 0.2s ease;
        }
        [data-testid="stBaseButton-primary"]:hover {
          background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
          box-shadow: 0 12px 28px rgba(245, 158, 11, 0.4);
          transform: translateY(-2px);
        }
        [data-testid="stBaseButton-primary"] p { color: #ffffff !important; font-weight: 600; font-size: 1.1rem; }

        /* ---- footer ------------------------------------------------------------ */
        .login-foot { text-align: center; color: #52525b; font-size: 0.9rem; margin-top: 2rem; font-weight: 500; }

        @media (max-width: 768px) {
          [data-testid="stMainBlockContainer"], .block-container { padding-top: 2rem; }
          .brand h1 { font-size: 2.2rem; }
        }
        </style>
        """
    )

    st.markdown(
        """
        <div class="brand">
          <div class="logo">🌾</div>
          <h1>YojanaAI</h1>
          <p class="sub">Discover · Optimize · Apply — welfare schemes for your whole family</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        tab_fam, tab_admin = st.tabs(["🧑‍🤝🧑 Family Portal", "👨‍💼 Admin Login"])

        with tab_fam:
            st.markdown(
                '<div class="panel-desc">Register your family profile, run the benefit optimizer, and securely track all your applications in one place.</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="chips">'
                '<span class="chip">Benefit Optimizer</span>'
                '<span class="chip">Regional Chat</span>'
                '<span class="chip">Doc Analysis</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            if st.button("Continue as Family", key="login_family", type="primary", use_container_width=True):
                sign_in_as("family")
                st.rerun()

        with tab_admin:
            st.markdown(
                '<div class="panel-desc">Government-side access for reviewing anonymized usage analytics and managing saved family records.</div>',
                unsafe_allow_html=True,
            )
            st.write("") # spacing
            admin_password = get_config("admin.password")
            if not admin_password:
                st.info("Admin access is not configured. Set ADMIN_PASSWORD in the deployment environment or admin.password in Streamlit secrets.")
            pw = st.text_input(
                "Administrator password",
                type="password",
                placeholder="Enter configured password",
                disabled=not admin_password,
            )
            if st.button(
                "Sign in as Admin",
                key="login_admin",
                type="primary",
                use_container_width=True,
                disabled=not admin_password,
            ):
                if pw == admin_password:
                    sign_in_as("admin")
                    st.rerun()
                else:
                    st.error("Incorrect password. Please try again.")

    st.markdown(
        '<div class="login-foot">Family sign-in is instant and passwordless · Admin access requires authorization</div>',
        unsafe_allow_html=True,
    )


def logout_page() -> None:
    st.caption("Signing you out…")
    sign_out()
    st.rerun()


def build_nav():
    role = current_role()
    if role == "admin":
        pages = [
            st.Page("pages/5_Analytics_Dashboard.py", title="Analytics Dashboard", icon="📈", default=True),
            st.Page("pages/6_Manage_Families.py", title="Manage Families", icon="🗂️"),
        ]
    else:  # family
        pages = [
            st.Page("pages/0_Home.py", title="Home", icon="🏠", default=True),
            st.Page("pages/1_Family_Registration.py", title="Family Registration", icon="🧑‍🤝‍🧑"),
            st.Page("pages/2_Optimizer_Results.py", title="Optimizer Results", icon="📊"),
            st.Page("pages/3_Regional_Chat.py", title="Regional Chat", icon="💬"),
            st.Page("pages/4_Document_Analysis.py", title="Document Analysis", icon="🪪"),
            st.Page("pages/7_My_Registrations.py", title="My Registrations", icon="📋"),
        ]
    pages.append(st.Page(logout_page, title="Log out", icon="🚪"))
    return st.navigation(pages)


if current_role():
    build_nav().run()
else:
    st.navigation([st.Page(login_page, title="Sign in", default=True)]).run()