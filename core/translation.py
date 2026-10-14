"""Regional-language translation layer.

Priority:
  1. Bhashini API (MeitY) when configured -- translate to/from Indian languages.
  2. MyMemory public API (no key needed; supports Hindi, Tamil, Telugu, Kannada,
     Malayalam, Marathi, Gujarati, Bengali, Punjabi, Odia, ...).
  3. Offline pass-through -- returns the text unchanged (marked) so the app still
     works with no connectivity / keys / unsupported language pair.

The chat page calls translate() twice (query -> English, answer -> regional) so
the answering logic never changes with language.
"""
from __future__ import annotations

import logging
import urllib.parse

import requests

from core import config

log = logging.getLogger(__name__)

SUPPORTED_MYMEMORY = {
    "en", "hi", "ta", "te", "kn", "ml", "mr", "gu", "bn", "pa", "or", "ur",
}

BASHINI_LANG_NAMES = {
    "hi": "hin", "bn": "ben", "ta": "tam", "te": "tel", "kn": "kan",
    "ml": "mal", "mr": "mar", "gu": "guj", "pa": "pan", "or": "ori",
    "as": "asm", "ur": "urd", "en": "eng",
}


def _detect_codes(language: str) -> tuple[str, str]:
    code = config.language_code(language)
    return ("en", code) if code != "en" else ("en", "en")


def translate(text: str, source: str, target: str, timeout: int = 30) -> dict:
    """Translate `text` from `source` to `target` language.

    Returns {"text": ..., "engine": "bhashini"|"mymemory"|"offline"|"noop"}.
    """
    src = config.language_code(source) if source != "auto" else "auto"
    tgt = config.language_code(target)
    if src == tgt:
        return {"text": text, "engine": "noop"}
    if not text or not text.strip():
        return {"text": text, "engine": "noop"}

    # 1) Bhashini
    if config.bhashini_configured():
        try:
            res = _bhashini(text, src, tgt, timeout)
            if res:
                return res
        except Exception:
            log.exception("Bhashini translation failed; trying fallback")

    # 2) MyMemory (no key)
    if src in SUPPORTED_MYMEMORY and tgt in SUPPORTED_MYMEMORY:
        try:
            res = _mymemory(text, src, tgt, timeout)
            if res:
                return res
        except Exception:
            log.exception("MyMemory translation failed; offline fallback")

    # 3) offline pass-through
    return {"text": text, "engine": "offline"}


def _bhashini(text: str, src: str, tgt: str, timeout: int) -> dict | None:
    src_hb = BASHINI_LANG_NAMES.get(src, src)
    tgt_hb = BASHINI_LANG_NAMES.get(tgt, tgt)
    payload = {
        "pipelineTasks": [
            {
                "taskType": "translation",
                "config": {
                    "language": {"sourceLanguage": src_hb, "targetLanguage": tgt_hb},
                    "serviceId": "ai4bharat/indictrans-v2-all-gpu--t4",
                },
            }
        ],
        "inputData": {"input": [{"source": text}]},
    }
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {config.get('bhashini.api_key', '')}",
        "x-api-key": config.get("bhashini.pipeline_api_key", "") or config.get("bhashini.api_key", ""),
        "user-id": config.get("bhashini.user_id", ""),
    }
    resp = requests.post(config.get("bhashini.endpoint"), json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    out = (data.get("pipelineResponse") or [{}])[0].get("output") or []
    translated = out[0].get("target", "").strip() if out else ""
    if translated:
        return {"text": translated, "engine": "bhashini"}
    return None


def _mymemory(text: str, src: str, tgt: str, timeout: int) -> dict | None:
    url = (
        "https://api.mymemory.translated.net/get"
        f"?q={urllib.parse.quote(text)}&langpair={src}|{tgt}"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    translated = (data.get("responseData") or {}).get("translatedText", "").strip()
    if translated and data.get("responseStatus") == 200:
        return {"text": translated, "engine": "mymemory"}
    return None


def translate_to_english(text: str, source_lang: str) -> tuple[str, dict]:
    res = translate(text, source_lang, "english")
    return res["text"], res


def translate_from_english(text: str, target_lang: str) -> tuple[str, dict]:
    res = translate(text, "english", target_lang)
    return res["text"], res