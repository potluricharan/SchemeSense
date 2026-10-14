# 🏛️ Family-Level Government Welfare Scheme Discovery & Eligibility Optimization Platform

Built on **Streamlit**, **Firebase (Firestore)**, **Google OR-Tools (CP-SAT)**, **Tesseract OCR**, and **ResNet50 + LangChain/Groq RAG**. All three phases are implemented and tested: the family optimizer, document intelligence, and a Plotly government-analytics dashboard with Docker containerization — anchored on the anonymized `usage_stats` layer.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- **Tesseract OCR** installed on your system:
  - **Ubuntu/Debian:** `sudo apt-get install tesseract-ocr`
  - **macOS:** `brew install tesseract`
  - **Windows:** Install via [UB-Mannheim Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki)

### Run Locally
```bash
pip install -r requirements.txt        # most already present on this machine
python tools/seed_schemes.py           # build 19 machine-checked scheme rules (data/scheme_rules.json)
python tools/ingest_dataset.py --sync  # load ALL 3,397 unique schemes from updated_data.csv (roster)
streamlit run app.py
```

Your `updated_data.csv` (3,400 rows → 3,397 unique schemes) is fully ingested: every scheme is browse-able and searchable from the home page and the regional chat. The 19 schemes with hand-encoded `eligibility_rules` additionally get verified eligibility badges and are the only ones the optimizer can safely reason over (the eligibility column is free text, so rules for all 3,400 would be guesses). Re-sync anytime with:

```bash
python tools/ingest_dataset.py --sync   # Firestore uses the cleanest slug as document id
```

---

## 🗺️ State-Wise Filtering

State names are extracted from each scheme's name/details/eligibility text into a `states` field (2,932 of the 3,397 rows mention a state; the rest stay "any"). 

- **Home Explorer:** Pick your state. State-level schemes are shown only if they mention that state, while Central schemes always apply to all states (toggleable via the *"Include Central schemes"* checkbox). 
- **Zero Cloud Reads for Browsing:** The roster snapshot ships as `data/scheme_roster.json` (read from disk, no Firestore reads), so browsing is cheap; verified schemes/profiles/usage-stats continue to use the cloud store.
- **Model Caching:** The first run downloads two ML models (once, cached): `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (chat retrieval) and `microsoft/resnet-50` (document classification).

---

## 🔐 Configuration

Keep credentials out of source control. Copy this template to `.streamlit/secrets.toml` and fill in only the values you use:

```toml
[admin]
password = "replace-with-a-strong-password"

[firebase]
project_id = ""
service_account_path = "serviceAccountKey.json"

[groq]
api_key = ""
model = "qwen/qwen3.8-27b"

[bhashini]
api_key = ""
user_id = ""
```

- The admin password can instead be provided through the `ADMIN_PASSWORD` environment variable.
- The service-account key and Streamlit secrets file are ignored by Git; never commit them.

---

## ☁️ Firestore (Live)

When Firebase credentials are configured, the app uses Cloud Firestore. If you recreate the database, push the rules again from the CLI:

```bash
python tools/seed_schemes.py --sync
```

> **Offline Fallback:** Without Firestore available, the app transparently falls back to local JSON (`data/local_db/`) — no code changes needed.

---

## 👥 Sign-In & Roles

The app opens on a sign-in gate (`app.py`) with two options:

1. **Family Portal (Passwordless):** A single **"Continue as Family"** button that leads straight into the family workspace (`pages/0_Home.py`) displaying their own state's schemes, plus a separate **📋 My Registrations** tracker (`pages/7_My_Registrations.py`) to record which schemes they applied for and the current status (*submitted → under review → approved*).
2. **Admin (Password-Protected):** Requires a password configured in deployment secrets; then only the admin pages appear: **Analytics Dashboard** and **Manage Families**. Family users never see these pages — the sidebar is rebuilt per role via `st.navigation`, so there are no "restricted" screens.

`core/roles.py` owns the gate (`require_role`, `require_any_role` are kept as a safety net for direct page access); signing out is a "Log out" entry in the sidebar.

---

## 🏗️ Architecture

```text
app.py                          # sign-in gate: Family Portal (passwordless) | Admin (password)
pages/0_Home.py                 # family workspace: their-state scheme explorer + registration tracker link
pages/1_Family_Registration.py  # dynamic family profile (+/± any number of members)
pages/2_Optimizer_Results.py    # rule screening → OR-Tools CP-SAT result + gap candidates
pages/3_Regional_Chat.py        # regional-language RAG chat
pages/4_Document_Analysis.py    # upload → OCR → classify → gap analysis (LLM + cross-check)
pages/7_My_Registrations.py     # family application tracker (add/update status/remove) — separate section
pages/5_Analytics_Dashboard.py  # ADMIN ONLY — Plotly government dashboard over anonymized usage_stats
pages/6_Manage_Families.py      # ADMIN ONLY — list / edit / delete every saved family + switch to it
api.py                          # FastAPI service: /health /schemes /optimize /stats

core/
  config.py        env / secrets.toml resolution
  db.py            Firestore ⇄ local-JSON store (auto-fallback)
  rules.py         scheme eligibility rule engine
  optimizer.py     OR-Tools CP-SAT benefit maximization
  translation.py   Bhashini → MyMemory → offline
  chat.py          LangChain + Groq RAG (embedding retrieval)
  ocr.py           Tesseract OCR → structured fields
  classifier.py    ResNet50 embeddings + keyword doc-type classification
  gap_analysis.py  RAG explanation + rule-based cross-check
  stats.py         anonymized usage_stats writer + loader for the dashboard
  roles.py         sign-in gate + per-role access control
  registrations.py family application tracker (local JSONL)

tools/curated_schemes.py  19 real schemes hand-encoded into eligibility_rules
tools/seed_schemes.py     merges CSV descriptions → data/scheme_rules.json / Firestore
tools/ingest_dataset.py   full updated_data.csv → data/scheme_roster.json / Firestore (3,397)
data/scheme_rules.json    generated rules table (verified, optimizer-ready)
data/scheme_roster.json   generated full dataset roster (browse/search, no rules)

deployment: Dockerfile · docker-compose.yml · .dockerignore · api.py
```

---

## 📊 Status & Capabilities

- **Family Optimization ✅** Streamlit UI, dynamic family registration, Firestore schema, OR-Tools optimization, regional chat over the full dataset.
- **Document Intelligence ✅** Tesseract OCR, ResNet50 + keyword classification, LangChain+Groq RAG gap analysis with rule cross-check, chatbot upgraded to full RAG.
- **Government Analytics ✅** Anonymized `usage_stats` written on every optimization/gap run and aggregated into a Plotly dashboard (`pages/5_Analytics_Dashboard.py`) with region filters, scheme-uptake and eligibility-mismatch charts (auto-seeds synthetic demo data when empty).
- **Deployment ✅** Containerized: Streamlit web + FastAPI backend as separate services (`docker-compose up --build`), software-only, no dedicated hardware.

---

## 📈 Dashboard & API

The **Analytics Dashboard** is admin-only: it filters by region, shows optimization/gap run volumes over time, top opted schemes, common eligibility mismatches, per-state activity and eligibility rates, plus an anonymized raw-sample table. Records only come from the app's own usage (no PII). Family users never see it.

The **FastAPI backend** exposes the same engine over HTTP:

```bash
uvicorn api:app --port 8000
curl localhost:8000/health
curl -X POST localhost:8000/optimize -H 'Content-Type: application/json' -d '{"profile": {...}}'
```

---

## 🐳 Docker Deployment

```bash
docker compose up --build            # web on :8501, api on :8000 (same tried-and-tested image)
# optional: docker compose run web python tools/seed_schemes.py --sync
```

- Secrets flow through environment variables (`GROQ_API_KEY`, `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_PATH`, `BHASHINI_API_KEY`, …); the service-account JSON is mounted read-only as a volume. 
- The roster ships inside the image (`data/scheme_roster.json`) so the UI works with zero cloud reads for the dataset — verified schemes, profiles and usage stats still hit Firestore.
- The generated identity-document samples in `demo_documents/` are intentionally not tracked. Regenerate them locally with `python demo_documents/make_demo_docs.py`.

---

## 🧪 Testing

```bash
# Regenerates rules; prints per-scheme screening on the demo family
python tools/seed_schemes.py

# UI smoke tests via streamlit.testing.v1.AppTest run on every page
pytest
```

---

## 📝 Notes

- `benefit_amount` values are indicative annualised INR used only by the optimizer.
- ResNet50 "fine-tuning" is implemented as few-shot centroids over `data/reference_images/<doc_type>/`; drop in a torch head on top of `core.classifier.embed` if you later obtain a labelled document set.
- No personal data is ever written to `usage_stats`; a new Bhashini key slots into `secrets.toml` with no code change.
