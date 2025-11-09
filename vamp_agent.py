#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vamp_agent.py — Enhanced Playwright agent with Outlook Office365 authentication fixes
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Error as PWError, TimeoutError as PWTimeout

# --------------------------------------------------------------------------------------
# Constants / Globals
# --------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
BRAIN_DIR = ROOT / "nwu_brain"
MANIFEST_PATH = BRAIN_DIR / "brain_manifest.json"

# Enhanced browser configuration for Outlook Office365
BROWSER_CONFIG = {
    "headless": False,
    "slow_mo": 200,  # Slower for better reliability with Office365
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

# Service-specific storage state paths and URLs
STATE_PATHS = {
    "outlook": ROOT / "outlook_state.json",
    "onedrive": ROOT / "onedrive_state.json",
    "drive": ROOT / "drive_state.json",
    # Add for Nextcloud if implemented: "nextcloud": ROOT / "nextcloud_state.json"
}

SERVICE_URLS = {
    "outlook": "https://outlook.office.com/mail/",
    "onedrive": "https://onedrive.live.com/",
    "drive": "https://drive.google.com/drive/my-drive",
    # Add for Nextcloud: "nextcloud": "https://your.nextcloud.instance/apps/files/"
}

# NWU Brain scorer
try:
    from nwu_brain.scoring import NWUScorer  # type: ignore
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

async def ensure_browser() -> None:
    """Launch persistent browser with Office365-compatible configuration."""
    global _PLAYWRIGHT, _BROWSER
    if _BROWSER is not None:
        return
        
    logger.info("Initializing Playwright browser with Office365 compatibility...")
    _PLAYWRIGHT = await async_playwright().start()
    _BROWSER = await _PLAYWRIGHT.chromium.launch(**BROWSER_CONFIG)

async def get_authenticated_context(service: str) -> Any:
    """Get or create an authenticated context using storage state."""
    state_path = STATE_PATHS.get(service)
    if not state_path:
        logger.warning(f"No state path defined for service: {service}")
        return await _BROWSER.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent=USER_AGENT,
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        )
    
    if not state_path.exists():
        logger.info(f"No storage state found for {service}. Prompting manual login...")
        context = await _BROWSER.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent=USER_AGENT,
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        )
        page = await context.new_page()
        await page.goto(SERVICE_URLS[service])
        
        # Detect login page and pause for manual input
        login_selector = {
            "outlook": 'input[name="loginfmt"]',  # Microsoft email input
            "onedrive": 'input[name="loginfmt"]',  # Same as Outlook
            "drive": 'input[type="email"]',  # Google email input
        }.get(service)

        if login_selector:
            input("Please complete login in the browser window, then press Enter here...")
            await context.storage_state(path=str(state_path))
        else:
            logger.warning(f"No login selector for {service}; skipping state save.")

        await page.close()
        return context

    # Load existing state
    return await _BROWSER.new_context(
        storage_state=str(state_path),
        viewport={'width': 1280, 'height': 800},
        user_agent=USER_AGENT,
        extra_http_headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    )

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

# --------------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------------

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
    
    if service in ["outlook", "onedrive", "drive"]:
        context = await get_authenticated_context(service)
    else:
        context = await _BROWSER.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent=USER_AGENT,
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        )
    
    await apply_stealth(context)
    
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
    await context.close()
    
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

from typing import Callable
import logging
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