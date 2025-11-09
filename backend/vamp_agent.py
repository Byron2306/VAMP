#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vamp_agent.py — Enhanced Playwright agent with Outlook Office365 authentication fixes
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import inspect
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Error as PWError, TimeoutError as PWTimeout

from . import BRAIN_DATA_DIR, STATE_DIR
from .nwu_brain.scoring import NWUScorer

# --------------------------------------------------------------------------------------
# Constants / Globals
# --------------------------------------------------------------------------------------

MANIFEST_PATH = BRAIN_DATA_DIR / "brain_manifest.json"

# Enhanced browser configuration for Outlook Office365
BROWSER_CONFIG = {
    "headless": True,
    "slow_mo": 0,
    "args": [
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor',
        '--disable-blink-features=AutomationControlled',
        '--disable-dev-shm-usage',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-component-extensions-with-background-pages',
        '--disable-default-apps',
        '--disable-extensions',
        '--disable-plugins',
        '--disable-translate',
        '--mute-audio',
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    ]
}

# User agent that looks like a real browser
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

# Keep a single shared browser across scans
_PLAYWRIGHT = None
_BROWSER = None
_CTX = None
_PAGES: Dict[str, Any] = {}
_SERVICE_CONTEXTS: Dict[str, Any] = {}
_CONTEXT_LOCK = asyncio.Lock()

# Service-specific storage state paths and URLs
STATE_DIR.mkdir(parents=True, exist_ok=True)

STATE_PATHS = {
    "outlook": STATE_DIR / "outlook_state.json",
    "onedrive": STATE_DIR / "onedrive_state.json",
    "drive": STATE_DIR / "drive_state.json",
    # Add for Nextcloud if implemented: "nextcloud": STATE_DIR / "nextcloud_state.json"
}

SERVICE_URLS = {
    "outlook": "https://outlook.office.com/mail/",
    "onedrive": "https://onedrive.live.com/",
    "drive": "https://drive.google.com/drive/my-drive",
    # Add for Nextcloud: "nextcloud": "https://your.nextcloud.instance/apps/files/"
}

ALLOW_INTERACTIVE_LOGIN = os.getenv("VAMP_ALLOW_INTERACTIVE_LOGIN", "1").strip().lower() not in {"0", "false", "no"}

# NWU Brain scorer
try:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Brain manifest not found: {MANIFEST_PATH}")
    SCORER = NWUScorer(str(MANIFEST_PATH))
except Exception as e:
    print(f"Warning: NWUScorer not available - {e}")
    class MockScorer:
        def compute(self, item):
            return {
                "kpa": ["KPA1"],
                "tier": ["Compliance"],
                "score": 3.0,
                "band": "Developing",
                "rationale": "Mock scoring - backend not available",
                "policy_hits": [],
                "must_pass_risks": []
            }
        def to_csv_row(self, item):
            return item
    SCORER = MockScorer()

# --------------------------------------------------------------------------------------
# Enhanced Browser Management with Authentication Fixes
# --------------------------------------------------------------------------------------

def _base_context_kwargs() -> Dict[str, Any]:
    return {
        'viewport': {'width': 1280, 'height': 800},
        'user_agent': USER_AGENT,
        'extra_http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    }


async def ensure_browser() -> None:
    """Launch persistent browser with Office365-compatible configuration."""
    global _PLAYWRIGHT, _BROWSER
    if _BROWSER is not None:
        return

    logger.info("Initializing Playwright browser with Office365 compatibility...")
    _PLAYWRIGHT = await async_playwright().start()
    _BROWSER = await _PLAYWRIGHT.chromium.launch(**BROWSER_CONFIG)

def _base_context_kwargs() -> Dict[str, Any]:
    return {
        'viewport': {'width': 1280, 'height': 800},
        'user_agent': USER_AGENT,
        'extra_http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    }


async def get_authenticated_context(service: str) -> Any:
    """Get or create an authenticated context using storage state."""
    await ensure_browser()

    key = service or "generic"

    async with _CONTEXT_LOCK:
        existing = _SERVICE_CONTEXTS.get(key)
        if existing is not None:
            try:
                if not existing.is_closed():
                    return existing
            except Exception:
                pass
            _SERVICE_CONTEXTS.pop(key, None)

        state_path = STATE_PATHS.get(service)
        context_kwargs = _base_context_kwargs()

        if state_path and state_path.exists():
            context_kwargs['storage_state'] = str(state_path)

        context = await _BROWSER.new_context(**context_kwargs)

        if state_path and not state_path.exists():
            if BROWSER_CONFIG.get("headless", True):
                await context.close()
                raise RuntimeError(
                    f"Storage state for {service} not found at {state_path}. "
                    "Headless mode requires a pre-authenticated storage_state file."
                )

            logger.info(f"No storage state found for {service}. Prompting manual login...")
            page = await context.new_page()
            await page.goto(SERVICE_URLS[service])

            login_selector = {
                "outlook": 'input[name="loginfmt"]',
                "onedrive": 'input[name="loginfmt"]',
                "drive": 'input[type="email"]',
            }.get(service)

            if login_selector:
                input("Please complete login in the browser window, then press Enter here...")
                await context.storage_state(path=str(state_path))
            else:
                logger.warning(f"No login selector for {service}; skipping state save.")

            await page.close()

        await apply_stealth(context)
        _SERVICE_CONTEXTS[key] = context
        return context

# --------------------------------------------------------------------------------------
# Stealth enhancements
# --------------------------------------------------------------------------------------

async def apply_stealth(context: Any) -> None:
    """Apply anti-detection measures."""
    await context.add_init_script("""
        delete window.navigator.webdriver;
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    """)


async def _prompt_manual_login(context: Any, service: str, state_path: Path) -> None:
    """Open a visible Chromium page and capture storage state after manual login."""

    url = SERVICE_URLS.get(service)
    if not url:
        raise RuntimeError(f"No login URL configured for {service}")

    page = await context.new_page()
    try:
        await page.goto(url, wait_until="load", timeout=60000)
    except Exception as exc:
        raise RuntimeError(f"Failed to load {url} for {service}: {exc}") from exc

    logger.info(
        "Storage state for %s not found. A visible Chromium window has been opened for manual login.",
        service,
    )
    prompt = (
        f"Complete the {service} sign-in flow in the opened Chromium window.\n"
        "Once your mailbox is visible, return to this terminal and press Enter to continue..."
    )

    try:
        input(prompt)
    except EOFError as exc:
        raise RuntimeError(
            "Interactive confirmation was not available while capturing the login session. "
            "Run the VAMP backend from a terminal where keyboard input is permitted or pre-create "
            f"the {service} storage_state file manually using Playwright's tooling."
        ) from exc

    state_path.parent.mkdir(parents=True, exist_ok=True)
    await context.storage_state(path=str(state_path))
    logger.info("Saved %s storage state to %s", service, state_path)

    try:
        await page.close()
    except Exception:
        pass


async def _ensure_storage_state(service: Optional[str], state_path: Optional[Path]) -> None:
    """Ensure a storage_state file exists; trigger interactive capture if necessary."""

    if not service or not state_path:
        return

    if state_path.exists():
        return

    if not BROWSER_CONFIG.get("headless", True):
        # Headful mode will allow the user to login during the scan itself.
        logger.info(
            "Storage state for %s missing but headless mode is disabled. Login during the scan will be required.",
            service,
        )
        return

    if not ALLOW_INTERACTIVE_LOGIN:
        raise RuntimeError(
            f"Storage state for {service} not found at {state_path}. "
            "Provide a pre-authenticated storage_state file or set VAMP_ALLOW_INTERACTIVE_LOGIN=1 to capture it interactively."
        )

    # Ensure Playwright is running so we can spawn a temporary visible browser.
    await ensure_browser()

    try:
        login_browser = await _PLAYWRIGHT.chromium.launch(
            headless=False,
            args=BROWSER_CONFIG.get("args", []),
        )
    except Exception as exc:
        raise RuntimeError(
            f"Storage state for {service} not found at {state_path} and a visible Chromium session could not be started ({exc}). "
            "Install the required Playwright browser dependencies for your platform or generate the storage_state file manually "
            "with Playwright before retrying."
        ) from exc

    login_context = await login_browser.new_context(**_base_context_kwargs())

    try:
        await apply_stealth(login_context)
        await _prompt_manual_login(login_context, service, state_path)
    finally:
        try:
            await login_context.close()
        except Exception:
            pass
        try:
            await login_browser.close()
        except Exception:
            pass

    if not state_path.exists():
        raise RuntimeError(
            f"Interactive login for {service} did not persist any credentials. "
            "Repeat the login flow and ensure you confirm completion in the terminal."
        )

# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------

async def _maybe_await(result: Any) -> None:
    """Await the result if it is awaitable."""
    if inspect.isawaitable(result):
        await result


async def _score_and_batch(
    items: List[Dict[str, Any]],
    sink: Callable[[List[Dict[str, Any]]], Any],
    on_progress: Optional[Callable[[float, str], Any]] = None,
    batch_size: int = 25,
) -> None:
    """Score items using the NWU brain and flush in batches via sink."""

    if not items:
        return

    total = len(items)
    pending: List[Dict[str, Any]] = []

    for idx, item in enumerate(items, start=1):
        title = item.get("title") or item.get("path") or ""
        platform = item.get("platform") or item.get("source") or ""
        timestamp = item.get("timestamp") or item.get("date") or item.get("modified") or ""

        item.setdefault("title", title)
        item.setdefault("source", platform or item.get("source") or "")
        item.setdefault("platform", platform)
        item.setdefault("path", item.get("path") or title)
        item.setdefault("relpath", item.get("relpath") or item.get("path") or title)
        if timestamp:
            item.setdefault("date", timestamp)
            item.setdefault("modified", timestamp)

        try:
            scored = SCORER.compute(item)
            item.update(scored)
            item["_scored"] = True
        except Exception as exc:
            logger.warning(f"Scoring failed for item {title or '[unnamed]'}: {exc}")
            item.setdefault("_scored", False)

        pending.append(item)

        if len(pending) >= batch_size:
            try:
                await _maybe_await(sink(list(pending)))
            finally:
                pending.clear()

        if on_progress:
            progress = 40 + (50 * (idx / total))
            capped = min(90, progress)
            await on_progress(capped, f"Scoring items ({idx}/{total})")

    if pending:
        await _maybe_await(sink(list(pending)))

    if on_progress:
        await on_progress(90, "Scoring complete")

async def _soft_scroll(page: Any, times: int = 5, delay: int = 500) -> None:
    """Smooth scroll to trigger lazy loading."""
    for _ in range(times):
        await page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
        await page.wait_for_timeout(delay)

def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def _parse_ts(ts_str: str) -> Optional[dt.datetime]:
    try:
        return dt.datetime.fromisoformat(ts_str)
    except Exception:
        pass
    try:
        return dt.datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    try:
        return dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    try:
        return dt.datetime.strptime(ts_str, "%m/%d/%Y %H:%M %p")
    except Exception:
        pass
    return None

def _in_month(ts: Optional[dt.datetime], month_bounds: Optional[Tuple[dt.date, dt.date]]) -> bool:
    if not ts or not month_bounds:
        return True
    start, end = month_bounds
    return start <= ts.date() < end

def _hash_from(source: str, path: str, timestamp: str = "") -> str:
    """Deterministic hash for dedup."""
    h = hashlib.sha1()
    h.update(source.encode("utf-8"))
    h.update(b"|")
    h.update(path.encode("utf-8"))
    h.update(b"|")
    h.update(timestamp.encode("utf-8"))
    return h.hexdigest()

async def _extract_element_text(page: Any, selector: str, timeout: int = 5000) -> str:
    """Extract text from first matching element."""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        el = await page.query_selector(selector)
        return await el.inner_text() or ""
    except Exception:
        return ""

# --------------------------------------------------------------------------------------
# Scrapers
# --------------------------------------------------------------------------------------

async def scrape_outlook(page: Any, month_bounds: Optional[Tuple[dt.date, dt.date]] = None) -> List[Dict[str, Any]]:
    """Outlook scraper with deep read and month filtering."""
    items = []
    await _soft_scroll(page, times=20)

    # Selectors for email rows
    rows = await page.query_selector_all('[role="listitem"]')
    for row in rows:
        try:
            subject = await _extract_element_text(row, '[aria-label*="Subject"]')
            sender = await _extract_element_text(row, '[aria-label*="From"]')
            ts_text = await _extract_element_text(row, '[aria-label*="Date"]')
            ts = _parse_ts(ts_text)
            if not _in_month(ts, month_bounds):
                continue
            item = {
                "source": "outlook",
                "path": f"{sender} - {subject}",
                "size": 0,  # Placeholder
                "timestamp": ts.isoformat() if ts else _now_iso()
            }
            item["hash"] = _hash_from(item["source"], item["path"], item.get("timestamp", ""))
            items.append(item)
            if len(items) >= 300:
                break
        except Exception:
            continue
    return items

async def scrape_onedrive(page: Any, month_bounds: Optional[Tuple[dt.date, dt.date]] = None) -> List[Dict[str, Any]]:
    """OneDrive scraper with deep read and month filtering."""
    items = []
    await _soft_scroll(page, times=15)

    rows = await page.query_selector_all('[role="row"]')
    for row in rows:
        try:
            name = await _extract_element_text(row, '[data-automationid="name"]')
            modified = await _extract_element_text(row, '[data-automationid="modified"]')
            ts = _parse_ts(modified)
            if not _in_month(ts, month_bounds):
                continue
            item = {
                "source": "onedrive",
                "path": name,
                "size": 0,
                "timestamp": ts.isoformat() if ts else _now_iso()
            }
            item["hash"] = _hash_from(item["source"], item["path"], item.get("timestamp", ""))
            items.append(item)
            if len(items) >= 300:
                break
        except Exception:
            continue
    return items

async def scrape_drive(page: Any, month_bounds: Optional[Tuple[dt.date, dt.date]] = None) -> List[Dict[str, Any]]:
    """Google Drive scraper with deep read and month filtering."""
    items = []
    await _soft_scroll(page, times=15)

    rows = await page.query_selector_all('[role="row"]')
    for row in rows:
        try:
            name = await _extract_element_text(row, '[data-column="name"]')
            modified = await _extract_element_text(row, '[data-column="lastModified"]')
            ts = _parse_ts(modified)
            if not _in_month(ts, month_bounds):
                continue
            item = {
                "source": "drive",
                "path": name,
                "size": 0,
                "timestamp": ts.isoformat() if ts else _now_iso()
            }
            item["hash"] = _hash_from(item["source"], item["path"], item.get("timestamp", ""))
            items.append(item)
            if len(items) >= 300:
                break
        except Exception:
            continue
    return items

async def scrape_efundi(page: Any, month_bounds: Optional[Tuple[dt.date, dt.date]] = None) -> List[Dict[str, Any]]:
    """eFundi scraper with month filtering."""
    items = []
    await _soft_scroll(page, times=10)

    # Cover common containers: table/list rows, portlet bodies, instructions, resource lists
    sels = [
        '[role="row"]',
        '.listHier',
        '.portletBody',
        '.instruction',
        '.listHier > li',
        'table.listHier tr'
    ]
    for sel in sels:
        nodes = await page.query_selector_all(sel)
        for el in nodes:
            txt = await el.inner_text() or ""
            if not txt or len(txt) < 5:
                continue
            first = (txt.split("\n")[0] or "")[0:160].strip()
            if not first:
                continue
            ts_text = await _extract_element_text(page, 'time, .date', timeout=3000)
            ts = _parse_ts(ts_text)
            if not _in_month(ts, month_bounds):
                continue
            item = {
                "source": "eFundi",
                "path": first,
                "size": 0,
                "timestamp": ts.isoformat() if ts else _now_iso()
            }
            item["hash"] = _hash_from(item["source"], item["path"], item.get("timestamp", ""))
            items.append(item)
            if len(items) >= 300:
                break
        if len(items) >= 300:
            break
    return items

# --------------------------------------------------------------------------------------
# Router and Main Scan Function
# --------------------------------------------------------------------------------------

async def run_scan_active(url: str, on_progress: Optional[Callable] = None, month_bounds: Optional[Tuple[dt.date, dt.date]] = None) -> List[Dict[str, Any]]:
    await ensure_browser()
    
    parsed_url = urlparse(url)
    host = parsed_url.hostname.lower() if parsed_url.hostname else ""
    
    if "outlook" in host or "office365" in host or "office" in host or "live" in host:
        service = "outlook"
    elif "sharepoint" in host or "onedrive" in host or "1drv" in host:
        service = "onedrive"
    elif "drive.google" in host:
        service = "drive"
    elif "efundi.nwu.ac.za" in host:
        service = "efundi"  # No auth needed, assume
    else:
        service = None
        logger.warning(f"Unsupported host: {host}")
        return []
    
    if on_progress:
        await on_progress(10, f"Authenticating to {service}...")
    
    try:
        if service in ["outlook", "onedrive", "drive"]:
            context = await get_authenticated_context(service)
        else:
            context = await get_authenticated_context(service or "generic")
    except Exception as e:
        logger.error(f"Context error: {e}")
        if on_progress:
            await on_progress(0, f"Authentication failed: {e}")
        return []

    page = await context.new_page()
    
    if on_progress:
        await on_progress(20, f"Navigating to {url}...")
    
    try:
        await page.goto(url, timeout=60000)
    except PWError as e:
        logger.error(f"Navigation failed: {e}")
        await context.close()
        return []
    
    if on_progress:
        await on_progress(30, "Loading content...")
    
    items = []
    if service == "outlook":
        items = await scrape_outlook(page, month_bounds)
    elif service == "onedrive":
        items = await scrape_onedrive(page, month_bounds)
    elif service == "drive":
        items = await scrape_drive(page, month_bounds)
    elif service == "efundi":
        items = await scrape_efundi(page, month_bounds)
    
    await page.close()
    
    if on_progress:
        await on_progress(40, "Processing items...")

    # Dedup and filter
    seen = set()
    deduped = []
    for it in items:
        h = it.get("hash")
        if h not in seen:
            seen.add(h)
            deduped.append(it)
    
    if on_progress:
        await _score_and_batch(deduped, lambda batch: None, on_progress)  # Score if needed
    
    return deduped

# --------------------------------------------------------------------------------------
# Type Definitions and Logger Setup
# --------------------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("vamp_agent")

# --------------------------------------------------------------------------------------
# SCAN_ACTIVE Wrapper for WebSocket integration
# --------------------------------------------------------------------------------------

async def run_scan_active_ws(email=None, year=None, month=None, url=None, deep_read=True, progress_callback=None):
    import datetime as dt
    from urllib.parse import urlparse

    if not url:
        if progress_callback:
            await progress_callback(0, "Missing URL.")
        return []

    # Month bounds for filtering
    try:
        if year and month:
            y, m = int(year), int(month)
            first_day = dt.date(y, m, 1)
            if m == 12:
                last_day = dt.date(y + 1, 1, 1)
            else:
                last_day = dt.date(y, m + 1, 1)
            month_bounds = (first_day, last_day)
        else:
            month_bounds = None
    except:
        month_bounds = None

    return await run_scan_active(url=url, month_bounds=month_bounds, on_progress=progress_callback)
