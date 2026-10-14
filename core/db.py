"""Data-access layer with an automatic Firestore / local-JSON fallback.

Backend selection:
  * firestore  -> when `serviceAccountKey.json` exists next to the project root
                  (Firebase Admin SDK credentials).
  * local      -> otherwise; schemes come from `data/scheme_rules.json`,
                  profiles & usage stats persist to `data/local_db/`.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path

from core import config

log = logging.getLogger(__name__)

SCHEME_RULES_JSON = config.PROJECT_ROOT / "data" / "scheme_rules.json"
SCHEME_ROSTER_JSON = config.PROJECT_ROOT / "data" / "scheme_roster.json"


def _line_id(line: str) -> str | None:
    try:
        return json.loads(line).get("id")
    except json.JSONDecodeError:
        return None


def scheme_states(scheme: dict) -> set[str]:
    """States a scheme applies to, from the ingested `states` list plus the
    older single `state` field (only kept when it is an explicit state)."""
    out = set(scheme.get("states") or [])
    st_name = scheme.get("state")
    if st_name and st_name != "any":
        out.add(st_name)
    return out


def schemes_for_state(state: str | None, schemes: list[dict]) -> list[dict]:
    """Schemes applicable to `state`: Central schemes always, plus only that
    state's own schemes. Other states' schemes are excluded. With no state,
    every scheme is returned."""
    if not state:
        return list(schemes)
    out = []
    for s in schemes:
        if s.get("level") == "Central" or state in scheme_states(s):
            out.append(s)
    return out


class DataStore:
    def __init__(self, backend: str):
        self.backend = backend
        self._client = None
        self.health = backend
        if backend == "firestore":
            self._init_firestore()
        else:
            self.local_root = config.PROJECT_ROOT / "data" / "local_db"
            self.local_root.mkdir(parents=True, exist_ok=True)

    # ---- setup ---------------------------------------------------------
    def _init_firestore(self):
        import firebase_admin
        from firebase_admin import credentials, firestore as fb_firestore

        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(
                    credentials.Certificate(str(config.service_account_path())),
                    {"projectId": config.firebase_project_id()},
                )
            self._client = fb_firestore.client()
            # connectivity / permissions probe (force iteration so the RPC runs)
            list(self._client.collection("scheme_rules").limit(1).stream())
            self.health = "firestore:ok"
        except Exception as exc:  # pragma: no cover
            log.warning("Firestore unavailable (%s); using local fallback", exc)
            self.health = f"firestore:error:{type(exc).__name__}"
            self.backend = "local"
            self.local_root = config.PROJECT_ROOT / "data" / "local_db"
            self.local_root.mkdir(parents=True, exist_ok=True)

    # ---- schemes -------------------------------------------------------
    def _degrade(self, exc: Exception) -> None:
        """Drop to the local backend when Firestore is not usable."""
        if self.backend != "firestore":
            return
        from google.api_core.exceptions import GoogleAPICallError

        if isinstance(exc, GoogleAPICallError):
            log.warning("Firestore error (%s); switching to local backend", exc)
            self.backend = "local"
            self.health = f"firestore:error:{type(exc).__name__}"
            self.local_root = config.PROJECT_ROOT / "data" / "local_db"
            self.local_root.mkdir(parents=True, exist_ok=True)

    def list_schemes(self) -> list[dict]:
        try:
            if self.backend == "firestore":
                docs = self._client.collection("scheme_rules").stream()
                return [dict(d.to_dict(), scheme_id=d.id) for d in docs]
        except Exception as exc:
            self._degrade(exc)
        if SCHEME_RULES_JSON.exists():
            with open(SCHEME_RULES_JSON, "r", encoding="utf-8") as fh:
                return json.load(fh)
        return []

    def get_scheme(self, scheme_id: str) -> dict | None:
        for s in self.list_schemes():
            if s.get("scheme_id") == scheme_id:
                return s
        return None

    def upsert_schemes(self, scheme_list: list[dict]) -> int:
        try:
            if self.backend == "firestore":
                col = self._client.collection("scheme_rules")
                batch = self._client.batch()
                written = 0
                for i, s in enumerate(scheme_list):
                    doc = col.document(s["scheme_id"])
                    batch.set(doc, s, merge=False)
                    written += 1
                    if written % 400 == 0:
                        batch.commit()
                        batch = self._client.batch()
                if written % 400 != 0:
                    batch.commit()
                return written
        except Exception as exc:
            self._degrade(exc)
        SCHEME_RULES_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEME_RULES_JSON, "w", encoding="utf-8") as fh:
            json.dump(scheme_list, fh, ensure_ascii=False, indent=2)
        return len(scheme_list)

    # ---- dataset roster (full updated_data.csv, no verified rules) ------
    def list_roster(self) -> list[dict]:
        """The 3,400-entry dataset snapshot ships as a static JSON file and is
        read from disk (zero Firestore reads); falls back to the cloud roster
        collection only when the local snapshot is missing."""
        if SCHEME_ROSTER_JSON.exists():
            with open(SCHEME_ROSTER_JSON, "r", encoding="utf-8") as fh:
                return json.load(fh)
        try:
            if self.backend == "firestore":
                docs = self._client.collection("scheme_roster").stream()
                return [dict(d.to_dict(), scheme_id=d.id) for d in docs]
        except Exception as exc:
            self._degrade(exc)
        return []

    def upsert_roster(self, roster: list[dict]) -> int:
        try:
            if self.backend == "firestore":
                col = self._client.collection("scheme_roster")
                batch = self._client.batch()
                written = 0
                for i, s in enumerate(roster):
                    doc = col.document(s["scheme_id"])
                    batch.set(doc, s, merge=False)
                    written += 1
                    if written % 400 == 0:
                        batch.commit()
                        batch = self._client.batch()
                if written % 400 != 0:
                    batch.commit()
                return written
        except Exception as exc:
            self._degrade(exc)
        SCHEME_ROSTER_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(SCHEME_ROSTER_JSON, "w", encoding="utf-8") as fh:
            json.dump(roster, fh, ensure_ascii=False, indent=2)
        return len(roster)

    def list_all_schemes(self) -> list[dict]:
        """Verified (rules_verified=True) schemes plus the full dataset roster."""
        verified = {s.get("scheme_id"): s for s in self.list_schemes()}
        merged = list(verified.values())
        for s in self.list_roster():
            if s.get("scheme_id") in verified:
                continue
            s = dict(s)
            s["rules_verified"] = False
            merged.append(s)
        return merged

    def count_roster(self) -> int:
        return len(self.list_roster())

    # ---- families ------------------------------------------------------
    def save_profile(self, profile: dict) -> str:
        profile = dict(profile)  # avoid mutating the caller's object
        pid = f"f_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        self._write_profile(pid, profile)
        return pid

    def update_profile(self, profile_id: str, profile: dict) -> bool:
        """Overwrite an existing family (same id), keeping its creation time."""
        profile = dict(profile)
        return self._write_profile(profile_id, profile, preserve_created=True)

    def delete_profile(self, profile_id: str) -> bool:
        try:
            if self.backend == "firestore":
                doc = self._client.collection("family_profiles").document(profile_id)
                if not doc.get().exists:
                    return False
                doc.delete()
                return True
        except Exception as exc:
            self._degrade(exc)
        path = self.local_root / "profiles.jsonl"
        if not path.exists():
            return False
        kept = [l for l in open(path, "r", encoding="utf-8")
                if not (_line_id(l) == profile_id)]
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(kept)
        return True

    def _write_profile(self, pid: str, profile: dict, preserve_created: bool = False) -> bool:
        created = time.time()
        if preserve_created:
            old = self.get_profile(pid)
            created = old.get("_created_at", created) if old else created
        doc = {
            "created_at": created,
            "profile": profile,
            "family_name": profile.get("family_name", ""),
            "state": profile.get("state", ""),
            "area": profile.get("area", ""),
            "annual_income": profile.get("annual_income", 0),
            "member_count": len(profile.get("members", []) or []),
        }
        try:
            if self.backend == "firestore":
                ref = self._client.collection("family_profiles").document(pid)
                payload = dict(doc)
                payload["members"] = profile.get("members", [])
                ref.set(payload, merge=True)
                return True
        except Exception as exc:
            self._degrade(exc)
        path = self.local_root / "profiles.jsonl"
        kept = []
        if path.exists():
            for line in open(path, "r", encoding="utf-8"):
                if _line_id(line) != pid:
                    kept.append(line)
        kept.append(json.dumps({"id": pid, **doc}, ensure_ascii=False) + "\n")
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(kept)
        return True

    def list_profiles(self) -> list[dict]:
        """Summaries of every saved family, newest first."""
        try:
            if self.backend == "firestore":
                docs = self._client.collection("family_profiles").order_by(
                    "created_at", direction="DESCENDING").stream()
                return [self._profile_summary(d.id, d.to_dict()) for d in docs]
        except Exception as exc:
            self._degrade(exc)
        path = self.local_root / "profiles.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in open(path, "r", encoding="utf-8"):
            try:
                item = json.loads(line)
                rows.append(item)
            except json.JSONDecodeError:
                continue
        rows.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
        return [self._profile_summary(r["id"], r) for r in rows]

    @staticmethod
    def _profile_summary(pid: str, data: dict) -> dict:
        pf = data.get("profile") or {}
        return {
            "profile_id": pid,
            "family_name": data.get("family_name") or pf.get("family_name") or "Unnamed family",
            "state": data.get("state") or pf.get("state", ""),
            "area": data.get("area") or pf.get("area", ""),
            "annual_income": data.get("annual_income") or pf.get("annual_income", 0),
            "member_count": data.get("member_count") or len(pf.get("members", []) or []),
            "created_at": data.get("created_at"),
            "members": data.get("members") or pf.get("members", []) or [],
        }

    def get_profile(self, profile_id: str) -> dict | None:
        try:
            if self.backend == "firestore":
                doc = self._client.collection("family_profiles").document(profile_id).get()
                if not doc.exists:
                    return None
                data = doc.to_dict()
                pf = dict(data.get("profile") or {})
                members = data.get("members") or [
                    m.to_dict()
                    for m in doc.reference.collection("family_members").order_by("order").stream()
                ]
                pf["members"] = members or []
                pf["_created_at"] = data.get("created_at")
                return pf
        except Exception as exc:
            self._degrade(exc)
        path = self.local_root / "profiles.jsonl"
        if not path.exists():
            return None
        for line in open(path, "r", encoding="utf-8"):
            item = json.loads(line)
            if item["id"] == profile_id:
                pf = dict(item.get("profile") or {})
                pf["members"] = item.get("members") or pf.get("members") or []
                pf["_created_at"] = item.get("created_at")
                return pf
        return None

    # ---- usage stats ---------------------------------------------------
    def add_usage_stat(self, stat: dict) -> None:
        try:
            if self.backend == "firestore":
                self._client.collection("usage_stats").document(stat["run_id"]).set(stat)
                return
        except Exception as exc:
            self._degrade(exc)
        path = self.local_root / "usage_stats.jsonl"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(stat, ensure_ascii=False) + "\n")

    def list_usage_stats(self) -> list[dict]:
        """All anonymized usage-stat rows (reverse chronological)."""
        try:
            if self.backend == "firestore":
                docs = self._client.collection("usage_stats").order_by("ts", direction="DESCENDING").stream()
                return [dict(d.to_dict()) for d in docs]
        except Exception as exc:
            self._degrade(exc)
        path = self.local_root / "usage_stats.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in open(path, "r", encoding="utf-8"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return rows


_STORE: DataStore | None = None
_STORE_FORCED = None


def get_store() -> DataStore:
    global _STORE
    if _STORE is None:
        backend = _STORE_FORCED or ("firestore" if config.firebase_configured() else "local")
        _STORE = DataStore(backend)
    return _STORE


def force_backend(backend: str):
    global _STORE, _STORE_FORCED
    _STORE_FORCED = backend
    _STORE = DataStore(backend)