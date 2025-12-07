"""
Local scan handler for VAMP WSActionDispatcher.

This module monkey patches WSActionDispatcher to add a SCAN_LOCAL action
that performs a local folder scan using vamp_master.scan_and_score. When
imported, the functions defined here will be attached to the dispatcher.
"""

import asyncio
import csv
import json
from pathlib import Path

# Import the dispatcher and scan_and_score. Note: relative imports are used
# because this file resides in backend/agent_app.
from .ws_dispatcher import WSActionDispatcher
from ..vamp_master import scan_and_score


def _handle_scan_local(self, sid: str, msg: dict) -> None:
    """Handle the SCAN_LOCAL action from the client.

    This method immediately emits a STARTED message and then schedules
    the asynchronous scan via _run_scan_local.

    Args:
        self: The WSActionDispatcher instance.
        sid: The websocket session ID.
        msg: The message payload containing folder_path, kpa, year, month.
    """
    # Notify client that scan is starting
    self._logger.info("SCAN_LOCAL requested")
    self._send_ws(sid, "SCAN_LOCAL/STARTED", {"message": "Local scan started"})
    # Kick off the asynchronous task
    self._start_async(self._run_scan_local(sid, msg))


async def _run_scan_local(self, sid: str, msg: dict) -> None:
    """Asynchronously perform a local folder scan.

    This method runs scan_and_score in a threadpool to avoid blocking
    the event loop, parses the resulting audit.csv, filters items by KPA,
    stores the evidence items, and emits a COMPLETE message.

    Args:
        self: The WSActionDispatcher instance.
        sid: The websocket session ID.
        msg: The message payload containing folder_path, kpa, year, month.
    """
    try:
        folder_path = msg.get("folder_path")
        if not folder_path:
        files = msg.get("files") or []
        if files:
            first = files[0]
            if isinstance(first, str) and '/' in first:                folder_path = first.split('/')[0]
            else:
                folder_path = str(first)
        else:
            raise ValueError("folder_path or files not provided for SCAN_LOCAL")

        kpa_filter = msg.get("kpa")
        year = msg.get("year")
        month = msg.get("month")

        # Offload the heavy scan to a thread executor
        loop = asyncio.get_running_loop()
        csv_path, report_path = await loop.run_in_executor(
            None, scan_and_score, folder_path, year, month
        )

        # Read the audit CSV and construct item dictionaries
        items = []
        csv_file = Path(csv_path)
        with csv_file.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row_kpa = row.get("kpa")
                # Apply KPA filter if specified and not "All"
                if kpa_filter and kpa_filter not in ("All", "all"):
                    if row_kpa != kpa_filter:
                        continue
                # Convert JSON-like fields safely
                def _load_json(val):
                    try:
                        return json.loads(val) if val else []
                    except Exception:
                        return []

                item = {
                    "kpa": [row_kpa] if row_kpa else [],
                    "name": row.get("doc"),
                    "path": row.get("relpath"),
                    "size": int(row.get("size")) if row.get("size") else None,
                    "modified": row.get("modified"),
                    "score": float(row.get("score")) if row.get("score") else None,
                    "policy_hits": _load_json(row.get("policy_hits")),
                    "must_pass_risks": _load_json(row.get("must_pass_risks")),
                }
                items.append(item)

        # Persist items if any
        if items:
            await self._store.add_items(items)

        # Send completion message with count
        self._send_ws(sid, "SCAN_LOCAL/COMPLETE", {"items": len(items)})
    except Exception as exc:
        # Log and notify client on error
        self._logger.error(f"Error during local scan: {exc}", exc_info=True)
        self._send_ws(sid, "SCAN_LOCAL/FAILED", {"error": str(exc)})


# Monkey patch the dispatcher with our new handlers. These assignments attach
# the functions to the class at import time so that dispatch() can find them.
WSActionDispatcher._handle_scan_local = _handle_scan_local  # type: ignore[attr-defined]
WSActionDispatcher._run_scan_local = _run_scan_local  # type: ignore[attr-defined]
