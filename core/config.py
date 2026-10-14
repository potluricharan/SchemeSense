"""Central configuration loader.

Resolves secrets from (in priority order):
  1. Environment variables
  2. .streamlit/secrets.toml  (so tools and the Streamlit app share one source)

Kept free of `streamlit` imports so command-line tools can run standalone.
"""
from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SECRETS_FILE = PROJECT_ROOT / ".streamlit" / "secrets.toml"

_LANGUAGE_ALIASES = {
    "english": "en", "hindi": "hi", "tamil": "ta", "telugu": "te",
    "kannada": "kn", "malayalam": "ml", "marathi": "mr", "gujarati": "gu",
    "bengali": "bn", "punjabi": "pa", "odia": "or", "assamese": "as",
    "urdu": "ur", "kashmiri": "ks", "sindhi": "sd", "nepali": "ne",
    "sanskrit": "sa", "maithili": "mai", "bodo": "brx", "santali": "sat",
    "dogri": "doi", "konkani": "kok", "manipuri": "mni", "tamil_english": "tamEng",
}

_HB_ALIASES = {"english": "en", "hindi": "hi", "tamil": "ta", "telugu": "te",
               "kannada": "kn", "malayalam": "ml", "marathi": "mr", "gujarati": "gu",
               "bengali": "bn", "punjabi": "pa", "odia": "or", "assamese": "as"}


def _load_secrets() -> dict:
    secrets: dict = {}
    if SECRETS_FILE.exists():
        with open(SECRETS_FILE, "rb") as fh:
            secrets = tomllib.load(fh)
    return secrets


def _get_env_secret(*names: str) -> str:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return ""


def get(key: str, default: str = "") -> str:
    """Get a dotted key (e.g. 'groq.api_key') from env or secrets file."""
    env_name = key.upper().replace(".", "_")
    val = _get_env_secret(env_name)
    if val:
        return val
    node = _load_secrets()
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node if isinstance(node, str) else (node or default)


def get_bool(key: str, default: bool = False) -> bool:
    v = get(key, "")
    if not v:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(get(key, ""))
    except (TypeError, ValueError):
        return default


def tesseract_cmd() -> str:
    cmd = get("tesseract.cmd", "")
    if cmd and os.path.exists(cmd):
        return cmd
    found = shutil.which("tesseract")
    if found:
        return found
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
              str(Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tesseract.exe")):
        if os.path.exists(p):
            return p
    return "tesseract"


def service_account_path() -> Path:
    p = Path(get("firebase.service_account_path", "serviceAccountKey.json"))
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def firebase_configured() -> bool:
    return bool(get("firebase.project_id", "")) and service_account_path().exists()


def firebase_project_id() -> str:
    return get("firebase.project_id", "")


def groq_api_key() -> str:
    return get("groq.api_key", "")


def groq_model() -> str:
    return get("groq.model", "qwen/qwen3.8-27b")


def bhashini_configured() -> bool:
    return bool(get("bhashini.api_key", "") and get("bhashini.user_id", ""))


def language_code(lang_name_or_code: str) -> str:
    """Map a language name (e.g. 'hind') or ISO code to the canonical code."""
    k = str(lang_name_or_code).strip().lower()
    if k in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[k]
    if k[-3:] == "hin":
        k = k[:-3]
    return k


def bhashini_code(lang_name_or_code: str) -> str:
    k = str(lang_name_or_code).strip().lower()
    code = _HB_ALIASES.get(k, k if len(k) == 2 else "")
    return code


def default_language() -> str:
    return get("app.default_language", "english")