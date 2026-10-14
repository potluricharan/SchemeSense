import streamlit as st

from core import config
from core.chat import answer
from core.db import get_store
from core.roles import require_any_role
from core.translation import translate

st.set_page_config(page_title="Regional Chat · YojanaAI", page_icon="💬", layout="wide")
require_any_role()


def inr_total(opt_result) -> str:
    try:
        v = float(opt_result.get("total_benefit", 0))
    except (TypeError, ValueError):
        v = 0
    return f"\u20b9{v:,.0f}"


st.title("3 · Regional-Language Scheme Chat")
st.caption("Query \u2192 Bhashini/MyMemory translate \u2192 RAG over all schemes (verified rules + full 3,397-row dataset) \u2192 translate back")

LANGS = ["english", "hindi", "tamil", "telugu", "kannada", "malayalam",
         "marathi", "gujarati", "bengali", "punjabi", "odia", "urdu"]

st.session_state.setdefault("chat_history", [])
st.session_state.setdefault("chat_lang", "english")

lang = st.selectbox("Your language", LANGS,
                    index=LANGS.index(st.session_state["chat_lang"]))
st.session_state["chat_lang"] = lang

profile = st.session_state.get("profile")
opt_result = st.session_state.get("opt_result")
store = get_store()
schemes = store.list_all_schemes()  # verified rules + full updated_data.csv roster

if not schemes:
    st.warning("No schemes found. Run `python tools/seed_schemes.py` first.")
    st.stop()

engine_note = ""
if lang != "english":
    probe = translate("hello", "english", lang)
    engine_note = f"Translation engine in use: **{probe['engine']}**."
    if probe["engine"] == "offline":
        engine_note += " (answers will stay in your language only when a translation service is reachable / key added)"

st.caption(engine_note if lang != "english" else "English mode — no translation wrapper applied.")

for msg in st.session_state["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("engine"):
            st.caption(f"engine: {msg['engine']}")

placeholder = "Ask about schemes, pensions, scholarships..."
if lang != "english":
    tr_res = translate(placeholder, "english", lang)
    placeholder = tr_res.get("text", placeholder)

user_input = st.chat_input(placeholder)
if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.spinner("Thinking..."):
        working_query = user_input
        if lang != "english":
            q_tr = translate(user_input, lang, "english")
            working_query = q_tr.get("text", user_input)

        reply = answer(working_query, schemes, profile=profile, opt_result=opt_result)

        final_text = reply["answer"]
        engines = []
        if lang != "english":
            out_tr = translate(reply["answer"], "english", lang)
            final_text = out_tr.get("text", reply["answer"])
            engines.append(f"translation:{out_tr['engine']}")
        engines.append(reply["engine"])

        # piping translated English back through machine MT can garble; show original too
        shown = final_text
        if lang != "english" and working_query != user_input:
            shown += f"\n\n---\n*(English answer: {reply['answer']})*"

    with st.chat_message("assistant"):
        st.markdown(shown)
        st.caption(f"engine: {', '.join(engines)} · sources: {', '.join(reply.get('sources', []))}")

    st.session_state["chat_history"].append({"role": "user", "content": user_input})
    st.session_state["chat_history"].append({"role": "assistant", "content": shown,
                                             "engine": ", ".join(engines)})

with st.sidebar:
    st.caption("Profile context for answers")
    if profile:
        st.write(f"Family: **{profile.get('family_name')}** ({profile.get('state')})")
        if opt_result:
            st.write(f"Optimized plan: {inr_total(opt_result)}/yr across {len(opt_result['chosen'])} schemes")

if st.sidebar.button("Clear chat"):
    st.session_state["chat_history"] = []
    st.rerun()