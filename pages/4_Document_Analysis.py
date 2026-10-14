import streamlit as st

from core import classifier, ocr, stats
from core.db import get_store
from core.gap_analysis import analyze
from core.roles import require_any_role
from core.ui_helpers import inr

st.set_page_config(page_title="Document Analysis · YojanaAI", page_icon="📄", layout="wide")
require_any_role()
st.title("4 · Document Gap Analysis")
st.caption("Upload a scanned/photographed document or PDF → OCR → classify → compare against a scheme rule → explain the gap")

schemes = get_store().list_schemes()
if not schemes:
    st.warning("scheme_rules is empty. Run `python tools/seed_schemes.py`.")
    st.stop()

profile = st.session_state.get("profile")

pending = st.session_state.get("pending_scheme")
pending_member = st.session_state.get("pending_member")

mcol, scol = st.columns([1, 2])
with mcol:
    member_name = None
    if profile and profile.get("members"):
        names = [m.get("name") or f"Member {i}" for i, m in enumerate(profile["members"])]
        if pending_member and pending_member in names:
            member_name = pending_member
        else:
            member_name = names[0]
        st.caption(f"Applying document to member: **{member_name}**")
    else:
        st.caption("No profile loaded — gap analysis still works against scheme rules.")

with scol:
    scheme_opts = {s["name"]: s["scheme_id"] for s in schemes}
    default_idx = 0
    if pending:
        default_idx = list(scheme_opts.values()).index(pending) if pending in scheme_opts.values() else 0
    chosen_name = st.selectbox("Scheme to check this document against",
                               list(scheme_opts.keys()), index=default_idx)
    scheme_id = scheme_opts[chosen_name]
    scheme = next(s for s in schemes if s["scheme_id"] == scheme_id)

st.write("---")
st.markdown(f"### 📄 Documents needed for **{scheme['name']}**")
doc_list = scheme.get("documents") or []
if doc_list:
    st.caption("Upload **all** of these documents together — select multiple files (Ctrl/Cmd + click) and "
               "the app **clubs them into one check**, merging the extracted details before the gap analysis.")
    for i, req_doc in enumerate(doc_list, 1):
        st.markdown(f"{i}. {req_doc}")
else:
    st.caption("No published document list for this scheme — upload any relevant proof "
               "(Aadhaar, income, caste, ration card).")

uploaded = st.file_uploader(
    "Upload the documents (images **or PDFs**) — multi-select to club them into one verification",
    type=["png", "jpg", "jpeg", "webp", "bmp", "pdf"], accept_multiple_files=True,
    help="Hold Ctrl (or Cmd on Mac) to select several files at once — e.g. Aadhaar + income + caste certificates. "
         "PDFs are supported: digital text is read directly, scanned pages are OCR'd automatically.",
)

c1, c2 = st.columns([1, 2])
with c1:
    if st.button("🧪 Load all demo documents", use_container_width=True):
        st.session_state["use_demo_docs"] = True
        st.rerun()
with c2:
    if st.session_state.get("use_demo_docs") and st.button("Clear demo documents", use_container_width=True):
        st.session_state.pop("use_demo_docs", None)
        st.session_state.pop("gap_result", None)
        st.rerun()

class DummyFile:
    def __init__(self, name, data):
        self.name = name
        self.data = data
    def getvalue(self):
        return self.data

files = []
if uploaded:
    files = list(uploaded)
    st.session_state.pop("use_demo_docs", None)
elif st.session_state.get("use_demo_docs"):
    from core.config import PROJECT_ROOT
    demo_dir = PROJECT_ROOT / "demo_documents"
    for p in demo_dir.glob("*.*"):
        if p.suffix.lower() in [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
            with open(p, "rb") as f:
                files.append(DummyFile(p.name, f.read()))

if not files:
    st.info("Tip: from the **Optimizer Results** page you can jump straight here with the "
            "failing scheme preselected ('Check my document for this scheme').")
    st.stop()

texts, fields_all, previews = [], {}, []
with st.spinner(f"Running OCR + classification on {len(files)} document(s)..."):
    from core.ocr import preview_image
    for f in files:
        data = f.getvalue()
        try:
            img = preview_image(data)
            previews.append((f.name, img))
        except Exception:
            pass
        d = ocr.extract_document(data)
        texts.append(d["text"])
        for k, v in d["fields"].items():
            fields_all.setdefault(k, v)
    doc = {"text": "\n\n".join(texts), "fields": fields_all}
    cl = classifier.classify(files[0].getvalue(), doc["text"])

if previews:
    st.caption(f"File(s) uploaded: {', '.join(n for n, _ in previews)}")
    pcols = st.columns(min(len(previews), 4))
    for i, (name, img) in enumerate(previews[:8]):
        with pcols[i % len(pcols)]:
            st.image(img, caption=name, width=200)

st.write("---")
h1, h2, h3 = st.columns(3)
with h1:
    st.metric("Detected type", cl["doc_type"].replace("_", " ").title())
with h2:
    st.metric("Confidence", f"{cl['confidence'] * 100:.0f}%")
with h3:
    st.metric("Methods", f"text:{cl['text_method']} / image:{cl['image_method']}")

with st.expander("Raw OCR text", expanded=False):
    st.code(doc["text"][:2000] or "(no text extracted)")

st.subheader("Extracted fields")
if doc["fields"]:
    st.dataframe(
        [{"field": k.replace("_", " ").title(), "value": str(v)} for k, v in doc["fields"].items()],
        hide_index=True, width="stretch",
    )
else:
    st.warning("No structured fields could be extracted — try a clearer scan.")

st.write("---")
st.subheader(f"Gap analysis for: {scheme['name']}")
st.caption(f"Benefit: {inr(scheme.get('benefit_amount', 0))}" + (
    "/yr" if scheme.get("benefit_period") == "yearly"
    else " (one-time)" if scheme.get("benefit_period") == "one_time" else ""))

if st.button("🔬 Run gap analysis (LangChain + Groq)", type="primary"):
    with st.spinner("Comparing extracted fields against the scheme rule, then generating explanation..."):
        result = analyze(scheme, profile or {}, doc["fields"], doc["text"])
        st.session_state["gap_result"] = result

        gap_category = result["gaps"][0]["field"] if result["gaps"] else "none"
        stats.record_gap_analysis_run(profile or {}, scheme_id, gap_category)

result = st.session_state.get("gap_result")
if result:
    st.markdown("### Explanation")
    if result["explanation"]:
        st.markdown(result["explanation"])
        st.caption(f"generated by: {result['engine']}")
    else:
        st.success("✅ No gaps left between the rule and the document — re-run the optimizer to confirm eligibility.")

    if result["gaps"]:
        st.markdown("### Detected gaps (rule engine cross-check)")
        for g in result["gaps"]:
            expected = g.get("expected")
            extracted = g.get("extracted")
            if isinstance(expected, list):
                expected = " or ".join(str(x) for x in expected)
            with st.popover(g["explainer"]):
                st.write(f"- Required condition: **{g['field']} {g['rule'].get('op')} {expected}**")
                st.write(f"- Extracted from document: **{extracted if extracted is not None else 'not found'}**")
                if g["mismatch"]:
                    st.warning(g["mismatch"])

if st.button("Clear this analysis"):
    st.session_state.pop("gap_result", None)
    st.session_state.pop("pending_scheme", None)
    st.rerun()