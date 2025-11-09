#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VAMP WebSocket Bridge — FINAL WORKING VERSION
Includes: SCAN_ACTIVE + ASK + ENROL + GET_STATE + FINALISE + EXPORT
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import traceback
from typing import Any, Dict, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from . import STORE_DIR
from .vamp_store import VampStore, _uid

# --- Import agent ---
try:
    from .vamp_agent import run_scan_active_ws
except Exception as e:
    logging.error(f"Failed to import vamp_agent: {e}")
    run_scan_active_ws = None

# --- Configuration ---
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("APP_PORT", "8765"))
STORE_DIR.mkdir(parents=True, exist_ok=True)
store = VampStore(str(STORE_DIR))

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("vamp.ws")

# --- Helpers ---
def ok(action: str, data: Any = None) -> str:
    payload = {"ok": True, "action": action}
    if data is not None:
        payload["data"] = data
    return json.dumps(payload)


def fail(action: str, error: Any) -> str:
    msg = str(error) if not isinstance(error, str) else error
    return json.dumps({"ok": False, "action": action, "error": msg})


def _uid_from(msg: Dict[str, Any]) -> str:
    email = (msg.get("email") or "").strip().lower()
    if email:
        return _uid(email)
    name = (msg.get("name") or "").strip().lower()
    org = (msg.get("org") or "nwu").strip().lower()
    return f"{name}@{org}" if name else "anon@nwu"


# --- Actions ---
async def on_enrol(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    email = msg.get("email", "").strip()
    name = msg.get("name", "").strip()
    org = msg.get("org", "NWU").strip()
    if not email:
        await ws.send(fail("ENROL", "Email required"))
        return
    try:
        profile = store.enroll(email, name, org)
        await ws.send(ok("ENROL", profile))
        logger.info(f"Enrolled: {email}")
    except Exception as e:
        await ws.send(fail("ENROL", str(e)))


async def on_get_state(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    uid = _uid_from(msg)
    year = int(msg.get("year", 2025))
    try:
        year_doc = store.get_year_doc(uid, year)
        await ws.send(ok("GET_STATE", {"year_doc": year_doc}))
    except Exception as e:
        await ws.send(fail("GET_STATE", str(e)))


async def on_finalise_month(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    uid = _uid_from(msg)
    year = int(msg.get("year", 2025))
    month = int(msg.get("month", 11))
    try:
        doc = store.finalise_month(uid, year, month)
        await ws.send(ok("FINALISE_MONTH", doc))
    except Exception as e:
        await ws.send(fail("FINALISE_MONTH", str(e)))


async def on_export_month(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    uid = _uid_from(msg)
    year = int(msg.get("year", 2025))
    month = int(msg.get("month", 11))
    try:
        path = store.export_month_csv(uid, year, month)
        await ws.send(ok("EXPORT_MONTH", {"path": str(path)}))
    except Exception as e:
        await ws.send(fail("EXPORT_MONTH", str(e)))


async def on_compile_year(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    uid = _uid_from(msg)
    year = int(msg.get("year", 2025))
    try:
        path = store.export_year_csv(uid, year)
        await ws.send(ok("COMPILE_YEAR", {"path": str(path)}))
    except Exception as e:
        await ws.send(fail("COMPILE_YEAR", str(e)))


async def on_scan_active(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    if run_scan_active_ws is None:
        await ws.send(fail("SCAN_ACTIVE", "vamp_agent not available"))
        return

    email = (msg.get("email") or "").strip().lower()
    uid = _uid(email) if email else _uid_from(msg)
    year = int(msg.get("year", 2025))
    month = int(msg.get("month", 11))
    url = msg.get("url") or "https://outlook.office365.com/mail/"
    deep_read = bool(msg.get("deep_read", True))

    logger.info(f"Starting scan for {uid}, {year}-{month:02d}, url={url}")

    await ws.send(ok("SCAN_ACTIVE/STARTED"))

    # Progress callback that sends updates over WebSocket
    async def on_progress(progress: float, status: str):
        try:
            await ws.send(ok("SCAN_ACTIVE/PROGRESS", {
                "progress": progress,
                "status": status
            }))
        except:
            pass  # Client may disconnect

    try:
        results = await run_scan_active_ws(
            email=email or uid,
            year=year,
            month=month,
            url=url,
            deep_read=deep_read,
            progress_callback=on_progress
        )

        if not results:
            await ws.send(ok("SCAN_ACTIVE/COMPLETE", {"added": 0, "total_evidence": 0}))
            return

        month_doc = store.add_items(uid, year, month, results)
        added = len(results)
        total = len(month_doc.get("items", []))

        await ws.send(ok("SCAN_ACTIVE/COMPLETE", {"added": added, "total_evidence": total}))
        logger.info(f"Scan complete: +{added}, total={total}")

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Scan failed: {tb}")
        await ws.send(fail("SCAN_ACTIVE", str(e)))


async def on_ask(ws: WebSocketServerProtocol, msg: Dict[str, Any]) -> None:
    messages = msg.get("messages", [])
    answer = f"[VAMP AI] Processed {len(messages)} messages."
    await ws.send(ok("ASK", {"answer": answer}))


# --- Handler ---
async def handler(ws: WebSocketServerProtocol, path: str) -> None:
    client_addr = f"{ws.remote_address[0]}:{ws.remote_address[1]}"
    logger.info(f"Client connected: {client_addr}")
    try:
        async for message in ws:
            try:
                msg = json.loads(message)
                action = msg.get("action", "").upper()

                if action == "ENROL":
                    await on_enrol(ws, msg)
                elif action == "GET_STATE":
                    await on_get_state(ws, msg)
                elif action == "FINALISE_MONTH":
                    await on_finalise_month(ws, msg)
                elif action == "EXPORT_MONTH":
                    await on_export_month(ws, msg)
                elif action == "COMPILE_YEAR":
                    await on_compile_year(ws, msg)
                elif action == "SCAN_ACTIVE":
                    await on_scan_active(ws, msg)
                elif action == "ASK":
                    await on_ask(ws, msg)
                else:
                    await ws.send(fail(action, "Unknown action"))

            except json.JSONDecodeError:
                await ws.send(fail("ERROR", "Invalid JSON"))
            except Exception as e:
                await ws.send(fail("ERROR", str(e)))
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Client disconnected: {client_addr}")
    except Exception as e:
        logger.error(f"Handler error: {e}")


# --- Server ---
async def main_async():
    logger.info(f"Starting VAMP WS Bridge on ws://{APP_HOST}:{APP_PORT}")
    async with websockets.serve(handler, APP_HOST, APP_PORT, ping_interval=20, ping_timeout=20):
        await asyncio.Future()  # Run forever


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")


if __name__ == "__main__":
    main()