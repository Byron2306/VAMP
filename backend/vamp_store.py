#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vamp_store.py — Enhanced Durable per-user storage for monthly evidence, locks, and CSV export
(NWU Brain–aligned)

FIXED: Method name consistency (enroll vs enrol)
FIXED: Added lock_month method for backward compatibility
FIXED: Enhanced error handling and logging
FIXED: Better path serialization for JSON responses
ADDED: Evidence retrieval methods for UI display and statistics
FIXED: Folder path – NO extra "users/" sub-folder, UID uses _at_

What this module does
---------------------
• Creates a lightweight on-disk store under: <base>/<uid>/<year>/<YYYY-MM>.json
• Each month JSON contains:
    {
      "year": 2025,
      "month": 11,
      "locked": false,
      "items": [ ... canonical/scored artefacts ... ],
      "updated_at": "...",
      "locked_at": "..."
    }
• Deduplication on add_items() by stable key:
    - Prefer hash (H::<sha1>); otherwise composite key K::<source>|<title>|<timestamp>
• Locking:
    - finalise_month() sets locked=true and triggers export_month_csv()
• Exports:
    - export_month_csv():  <base>/<uid>/<year>/reports/<YYYY>-<MM>-evidence.csv
    - export_year_csv():   <base>/<uid>/<year>/reports/<YYYY>-evidence-yearly.csv
      (merged monthly rows, with an extra _month column)

CSV V2 columns (authoritative fields)
-------------------------------------
source, title, date, platform, relpath, size, modified, hash, snippet, meta,
kpa, tier, tier_rule, values_score, values_hits,
policy_hits, policy_hit_details, must_pass_risks,
score, band, rationale, actions
"""

from __future__ import annotations

import csv
import json
import os
import re
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import logging

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
logger = logging.getLogger("vamp.store")

# ----------------------------------------------------------------------
# Helper – safe UID from e-mail
# ----------------------------------------------------------------------
def _uid(email: str) -> str:
    """
    Convert an e-mail address into a safe folder name.
    byron.bunt@nwu.ac.za → byron.bunt_at_nwu.ac.za
    """
    email = email.strip().lower()
    email = email.replace("@", "_at_")                     # keep the @ meaning
    email = re.sub(r'[<>:"/\\|?*]', "", email)            # remove illegal chars
    return email


# ----------------------------------------------------------------------
# VampStore
# ----------------------------------------------------------------------
class VampStore:
    """Per-user JSON storage with month-level locking and CSV export."""

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(self, base_dir: str | Path = "data"):
        self.base_dir = Path(base_dir).resolve()
        os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"VampStore initialized at {self.base_dir}")

    # ------------------------------------------------------------------
    # Path helpers (NO extra "users/" folder)
    # ------------------------------------------------------------------
    def _user_dir(self, email: str) -> Path:
        """<base>/<uid>/"""
        uid = _uid(email)
        return self.base_dir / uid

    def get_profile_path(self, email: str) -> Path:
        return self._user_dir(email) / "profile.json"

    def get_year_dir(self, email: str, year: int) -> Path:
        return self._user_dir(email) / str(year)

    def get_month_dir(self, email: str, year: int, month: int) -> Path:
        return self.get_year_dir(email, year) / f"{month:02d}"

    def get_month_path(self, email: str, year: int, month: int) -> Path:
        return self.get_month_dir(email, year, month) / "month.json"

    def get_items_path(self, email: str, year: int, month: int) -> Path:
        return self.get_month_dir(email, year, month) / "items.json"

    def get_reports_dir(self, email: str, year: int) -> Path:
        d = self.get_year_dir(email, year) / "reports"
        os.makedirs(d, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # JSON I/O utilities
    # ------------------------------------------------------------------
    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            return {}

    @staticmethod
    def _save_json(path: Path, data: Dict[str, Any]) -> None:
        os.makedirs(path.parent, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp.replace(path)
        except Exception as e:
            logger.error(f"Failed to save {path}: {e}")
            raise

    # ------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------
    def enroll(self, email: str, name: str = "", org: str = "NWU") -> Dict[str, Any]:
        """
        Create (or refresh) a user profile.
        Returns the profile dict.
        """
        uid = _uid(email)
        profile_path = self.get_profile_path(email)

        profile = {
            "email": email,
            "uid": uid,
            "name": name or email.split("@")[0],
            "org": org,
            "enrolled_at": datetime.utcnow().isoformat() + "Z",
        }

        self._save_json(profile_path, profile)
        logger.info(f"Enrolled user {email} → {uid}")
        return profile

    # ------------------------------------------------------------------
    # Month document handling
    # ------------------------------------------------------------------
    def _ensure_month_doc(self, email: str, year: int, month: int) -> Dict[str, Any]:
        path = self.get_month_path(email, year, month)
        doc = self._load_json(path)

        if not doc:
            doc = {
                "year": year,
                "month": month,
                "locked": False,
                "items": [],
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }
            self._save_json(path, doc)
        return doc

    # ------------------------------------------------------------------
    # Deduplication key
    # ------------------------------------------------------------------
    @staticmethod
    def _dedup_key(item: Dict[str, Any]) -> str:
        """Stable key: H::<hash> or K::<source>|<title>|<timestamp>"""
        h = item.get("hash")
        if h and isinstance(h, str) and len(h) > 8:
            return f"H::{h}"
        src = item.get("source", "")
        title = item.get("title", "")
        ts = item.get("date") or item.get("modified") or ""
        return f"K::{src}|{title}|{ts}"

    # ------------------------------------------------------------------
    # Add items (with deduplication)
    # ------------------------------------------------------------------
    def add_items(
        self,
        email: str,
        year: int,
        month: int,
        new_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Append items to the month, deduplicate, and return the updated month doc.
        """
        month_doc = self._ensure_month_doc(email, year, month)
        existing_keys = {self._dedup_key(it) for it in month_doc.get("items", [])}
        added = 0

        for it in new_items:
            key = self._dedup_key(it)
            if key not in existing_keys:
                month_doc.setdefault("items", []).append(it)
                existing_keys.add(key)
                added += 1

        if added:
            month_doc["updated_at"] = datetime.utcnow().isoformat() + "Z"
            self._save_json(self.get_month_path(email, year, month), month_doc)

        logger.info(
            f"Added {added} new items for {email} {year}-{month:02d} "
            f"(total {len(month_doc['items'])})"
        )
        return month_doc

    # ------------------------------------------------------------------
    # Finalise / lock a month
    # ------------------------------------------------------------------
    def finalise_month(self, email: str, year: int, month: int) -> Dict[str, Any]:
        """Lock the month and export CSV."""
        month_doc = self._ensure_month_doc(email, year, month)
        if month_doc.get("locked"):
            logger.info(f"Month {year}-{month:02d} already locked for {email}")
            return month_doc

        month_doc["locked"] = True
        month_doc["locked_at"] = datetime.utcnow().isoformat() + "Z"
        self._save_json(self.get_month_path(email, year, month), month_doc)

        # Export CSV automatically
        try:
            csv_path = self.export_month_csv(email, year, month)
            logger.info(f"Exported locked month CSV: {csv_path}")
        except Exception as e:
            logger.error(f"CSV export failed after lock: {e}")

        return month_doc

    # Backward-compatibility alias
    lock_month = finalise_month

    # ------------------------------------------------------------------
    # CSV Export – month
    # ------------------------------------------------------------------
    def export_month_csv(self, email: str, year: int, month: int) -> Path:
        month_doc = self._ensure_month_doc(email, year, month)
        items = month_doc.get("items", [])

        csv_path = self.get_reports_dir(email, year) / f"{year}-{month:02d}-evidence.csv"

        # Deterministic column order (authoritative + legacy)
        authoritative = [
            "kpa",
            "tier",
            "tier_rule",
            "values_score",
            "values_hits",
            "policy_hits",
            "policy_hit_details",
            "must_pass_risks",
            "score",
            "band",
            "rationale",
            "actions",
        ]
        legacy = [
            "source",
            "title",
            "date",
            "platform",
            "relpath",
            "size",
            "modified",
            "hash",
            "snippet",
            "meta",
        ]
        headers = legacy + [c for c in authoritative if c not in legacy]

        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for it in items:
                row = {}
                for k in headers:
                    row[k] = it.get(k, "")
                # Ensure list fields become comma-separated strings
                for k in ("kpa", "tier"):
                    if isinstance(row[k], list):
                        row[k] = ",".join(row[k])
                writer.writerow(row)

        logger.info(f"Month CSV exported: {csv_path}")
        return csv_path

    # ------------------------------------------------------------------
    # CSV Export – whole year
    # ------------------------------------------------------------------
    def export_year_csv(self, email: str, year: int) -> Path:
        year_dir = self.get_year_dir(email, year)
        if not year_dir.is_dir():
            raise FileNotFoundError(f"No data for {email} {year}")

        all_rows: List[Dict[str, Any]] = []
        for month in range(1, 13):
            month_path = self.get_month_path(email, year, month)
            if not month_path.is_file():
                continue
            doc = self._load_json(month_path)
            for it in doc.get("items", []):
                row = {"_month": month}
                row.update(it)
                all_rows.append(row)

        csv_path = self.get_reports_dir(email, year) / f"{year}-evidence-yearly.csv"

        # Same column order as month export + _month at the front
        authoritative = [
            "kpa",
            "tier",
            "tier_rule",
            "values_score",
            "values_hits",
            "policy_hits",
            "policy_hit_details",
            "must_pass_risks",
            "score",
            "band",
            "rationale",
            "actions",
        ]
        legacy = [
            "source",
            "title",
            "date",
            "platform",
            "relpath",
            "size",
            "modified",
            "hash",
            "snippet",
            "meta",
        ]
        headers = ["_month"] + legacy + [
            c for c in authoritative if c not in legacy
        ]

        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for row in all_rows:
                # flatten lists
                for k in ("kpa", "tier"):
                    if isinstance(row.get(k), list):
                        row[k] = ",".join(row[k])
                writer.writerow(row)

        logger.info(f"Year CSV exported: {csv_path}")
        return csv_path

    # ------------------------------------------------------------------
    # Evidence retrieval for UI
    # ------------------------------------------------------------------
    def get_evidence_for_display(
        self, email: str, year: int, month: int
    ) -> List[Dict[str, Any]]:
        """Return the list of items for the UI table."""
        path = self.get_items_path(email, year, month)
        data = self._load_json(path)
        return data.get("items", [])

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------
    def get_evidence_stats(self, email: str, year: int) -> Dict[str, Any]:
        """Year-level stats: total items, avg score, locked months, etc."""
        stats = {
            "year": year,
            "total_items": 0,
            "scored_items": 0,
            "average_score": 0.0,
            "locked_months": [],
            "unlocked_months": [],
        }

        for m in range(1, 13):
            month_doc = self._load_json(self.get_month_path(email, year, m))
            if not month_doc:
                continue
            items = month_doc.get("items", [])
            stats["total_items"] += len(items)
            locked = month_doc.get("locked", False)
            (stats["locked_months"] if locked else stats["unlocked_months"]).append(m)

            for it in items:
                score = it.get("score")
                if isinstance(score, (int, float)):
                    stats["scored_items"] += 1
                    stats["average_score"] += score

        if stats["scored_items"]:
            stats["average_score"] /= stats["scored_items"]
        else:
            stats["average_score"] = None

        return stats

    # ------------------------------------------------------------------
    # Year document (for GET_STATE)
    # ------------------------------------------------------------------
    def get_year_doc(self, email: str, year: int) -> Dict[str, Any]:
        """Return lightweight year metadata for dashboards."""
        year_dir = self.get_year_dir(email, year)
        if not year_dir.is_dir():
            return {"year": year, "months": {}}

        months: Dict[str, Any] = {}
        for m in range(1, 13):
            month_path = self.get_month_path(email, year, m)
            if not month_path.is_file():
                continue
            doc = self._load_json(month_path)
            months[str(m)] = {
                "month": m,
                "locked": doc.get("locked", False),
                "item_count": len(doc.get("items", [])),
                "updated_at": doc.get("updated_at"),
                "locked_at": doc.get("locked_at"),
            }

        return {"year": year, "months": months}

    def get_year_doc_with_items(self, email: str, year: int) -> Dict[str, Any]:
        """Return a year document that includes month-level evidence items."""

        base = self.get_year_doc(email, year)
        months: Dict[str, Any] = {}
        total_items = 0

        for month_key, meta in base.get("months", {}).items():
            try:
                month_int = int(month_key)
            except (TypeError, ValueError):
                continue

            month_doc = self._load_json(self.get_month_path(email, year, month_int))
            if not month_doc:
                month_doc = {}

            items = list(month_doc.get("items", []))

            meta_with_items = dict(meta)
            locked_flag = month_doc.get("locked")
            if locked_flag is None:
                locked_flag = meta.get("locked", False)
            meta_with_items["locked"] = bool(locked_flag)
            meta_with_items["updated_at"] = month_doc.get("updated_at") or meta.get("updated_at")
            meta_with_items["locked_at"] = month_doc.get("locked_at") or meta.get("locked_at")
            meta_with_items["items"] = items

            total_items += len(items)
            months[month_key] = meta_with_items

        return {"year": year, "months": months, "total_items": total_items}


# ----------------------------------------------------------------------
# Test Function (run with `python vamp_store.py`)
# ----------------------------------------------------------------------
def test_store():
    """Quick sanity-check of the store."""
    print("Testing VampStore...")

    store = VampStore()

    # 1. Enrol
    try:
        profile = store.enroll("test@nwu.ac.za", "Test User", "NWU")
        print(f"Enrolled: {profile['email']} → {profile['uid']}")
    except Exception as e:
        print(f"Enrol failed: {e}")
        return

    # 2. Add items
    try:
        items = [
            {
                "source": "outlook",
                "title": "Meeting notes",
                "hash": "abc123",
                "score": 4.2,
                "kpa": ["KPA1"],
            },
            {
                "source": "outlook",
                "title": "Project update",
                "hash": "def456",
                "score": 3.7,
                "kpa": ["KPA2", "KPA3"],
            },
        ]
        doc = store.add_items("test@nwu.ac.za", 2025, 11, items)
        print(f"Added {len(doc['items'])} items")
    except Exception as e:
        print(f"Add failed: {e}")
        return

    # 3. Export
    try:
        csv_path = store.export_month_csv("test@nwu.ac.za", 2025, 11)
        print(f"CSV: {csv_path}")
    except Exception as e:
        print(f"Export failed: {e}")
        return

    # 4. Finalise
    try:
        locked = store.finalise_month("test@nwu.ac.za", 2025, 11)
        print(f"Locked: {locked['locked']}")
    except Exception as e:
        print(f"Finalise failed: {e}")
        return

    print("All tests passed!")


if __name__ == "__main__":
    test_store()