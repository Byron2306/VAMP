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
import io
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

OCR_AVAILABLE = False
_OCR_ERROR: Optional[str] = None

try:
    from PIL import Image  # type: ignore
    import pytesseract  # type: ignore

    try:
        pytesseract.get_tesseract_version()
        OCR_AVAILABLE = True
    except Exception as exc:  # pragma: no cover - environment dependent
        OCR_AVAILABLE = False
        _OCR_ERROR = str(exc)
except Exception as exc:  # pragma: no cover - optional dependency
    Image = None  # type: ignore
    pytesseract = None  # type: ignore
    OCR_AVAILABLE = False
    _OCR_ERROR = str(exc)

from . import BRAIN_DATA_DIR, STATE_DIR
from .vamp_store import _uid
from .nwu_brain.scoring import NWUScorer

# --------------------------------------------------------------------------------------
# Constants / Globals
# --------------------------------------------------------------------------------------

MANIFEST_PATH = BRAIN_DATA_DIR / "brain_manifest.json"

# Enhanced browser configuration for Outlook Office365
BROWSER_CONFIG = {
    "headless": os.getenv("VAMP_HEADLESS", "1").strip().lower() not in {"0", "false", "no"},
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

# Optional credential-based automation (service -> env var names)
SERVICE_CREDENTIAL_ENV = {
    "outlook": {
        "username": os.getenv("VAMP_OUTLOOK_USERNAME", "").strip(),
        "password": os.getenv("VAMP_OUTLOOK_PASSWORD", "").strip(),
    },
    "onedrive": {
        "username": os.getenv("VAMP_ONEDRIVE_USERNAME", "").strip(),
        "password": os.getenv("VAMP_ONEDRIVE_PASSWORD", "").strip(),
    },
    "drive": {
        "username": os.getenv("VAMP_GOOGLE_USERNAME", "").strip(),
        "password": os.getenv("VAMP_GOOGLE_PASSWORD", "").strip(),
    },
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

LEGACY_STATE_PATHS = {
    "outlook": STATE_DIR / "outlook_state.json",
    "onedrive": STATE_DIR / "onedrive_state.json",
    "drive": STATE_DIR / "drive_state.json",
}

SERVICE_STATE_DIRS = {
    "outlook": STATE_DIR / "outlook",
    "onedrive": STATE_DIR / "onedrive",
    "drive": STATE_DIR / "drive",
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


def _state_path_for(service: Optional[str], identity: Optional[str]) -> Optional[Path]:
    if not service:
        return None

    base = SERVICE_STATE_DIRS.get(service)
    if not base:
        return None

    base.mkdir(parents=True, exist_ok=True)

    safe_identity = _uid(identity) if identity else "default"
    state_path = base / f"{safe_identity}.json"

    # Migrate legacy single-state files if present
    legacy = LEGACY_STATE_PATHS.get(service)
    if legacy and legacy.exists() and not state_path.exists():
        try:
            import shutil

            shutil.copy2(legacy, state_path)
            logger.info("Migrated legacy %s storage state from %s", service, legacy)
        except Exception as exc:
            logger.warning("Failed to migrate legacy %s storage state: %s", service, exc)

    return state_path


async def get_authenticated_context(service: str, identity: Optional[str] = None) -> Any:
    """Get or create an authenticated context using storage state."""
    await ensure_browser()

    identity_key = _uid(identity) if identity else "default"
    key = f"{service}:{identity_key}" if service else f"generic:{identity_key}"

    async with _CONTEXT_LOCK:
        existing = _SERVICE_CONTEXTS.get(key)
        if existing is not None:
            try:
                if not existing.is_closed():
                    logger.info(
                        "Reusing cached %s context with saved state for %s",
                        service or "generic",
                        identity or "default",
                    )
                    return existing
            except Exception:
                pass
            _SERVICE_CONTEXTS.pop(key, None)

        state_path = _state_path_for(service, identity)
        context_kwargs = _base_context_kwargs()

        await _ensure_storage_state(service, state_path, identity)

        if state_path and state_path.exists():
            context_kwargs['storage_state'] = str(state_path)
            logger.info("Using %s storage state from %s", service, state_path)

        context = await _BROWSER.new_context(**context_kwargs)

        if state_path and not state_path.exists():
            if BROWSER_CONFIG.get("headless", True):
                await context.close()
                raise RuntimeError(
                    f"Storage state for {service} not found at {state_path}. "
                    "Headless mode requires a pre-authenticated storage_state file."
                )

            logger.info(f"No storage state found for {service} ({identity or 'default'}). Prompting manual login...")
            page = await context.new_page()
            await page.goto(SERVICE_URLS[service])

            login_selector = {
                "outlook": 'input[name="loginfmt"]',
                "onedrive": 'input[name="loginfmt"]',
                "drive": 'input[type="email"]',
            }.get(service)

            if login_selector:
                input(
                    f"Complete the {service} sign-in for {identity or 'this account'} in the browser window, then press Enter here..."
                )
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


def _credentials_for(service: Optional[str], identity: Optional[str]) -> Optional[Tuple[str, str]]:
    if not service:
        return None

    service_conf = SERVICE_CREDENTIAL_ENV.get(service, {})
    username = service_conf.get("username") or (identity or "").strip()
    password = service_conf.get("password")

    if username and password:
        return username, password

    logger.debug("No credentials available for automated %s login", service)
    return None


async def _dismiss_kmsi_prompt(page: Any) -> None:
    """Dismiss the 'Stay signed in?' prompt if it appears."""

    try:
        await page.wait_for_selector('input[id="idBtn_Back"]', timeout=5000)
        await page.click('input[id="idBtn_Back"]')
        return
    except PWTimeout:
        pass

    try:
        await page.wait_for_selector('button#idBtn_Back, button[data-report-value="No"]', timeout=3000)
        await page.click('button#idBtn_Back, button[data-report-value="No"]')
    except PWTimeout:
        pass


async def _try_nwu_adfs_login(page: Any, username: str, password: str) -> bool:
    """Attempt to authenticate against the NWU ADFS portal if detected."""

    selectors = [
        '#userNameInput',
        'input[name="UserName"]',
    ]
    password_selectors = [
        '#passwordInput',
        'input[name="Password"]',
    ]

    user_selector = None
    for candidate in selectors:
        try:
            await page.wait_for_selector(candidate, timeout=2000)
            user_selector = candidate
            break
        except PWTimeout:
            continue

    if not user_selector:
        return False

    logger.info("Detected NWU ADFS login flow; attempting automated authentication.")

    password_selector = None
    for candidate in password_selectors:
        try:
            await page.wait_for_selector(candidate, timeout=2000)
            password_selector = candidate
            break
        except PWTimeout:
            continue

    if not password_selector:
        logger.warning("NWU ADFS login detected but password field not found; falling back to manual flow.")
        return False

    await page.fill(user_selector, username)
    await page.fill(password_selector, password)

    submit_selectors = [
        '#submitButton',
        'input[type="submit"]#submitButton',
        'button[type="submit"]#submitButton',
        'input[type="submit"]',
        'button[type="submit"]',
    ]

    clicked = False
    for candidate in submit_selectors:
        try:
            element = await page.query_selector(candidate)
            if element:
                await element.click()
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        await page.press(password_selector, "Enter")

    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass

    return True


async def _wait_for_outlook_ready(page: Any) -> None:
    """Wait until the Outlook mailbox UI is available."""

    await _dismiss_kmsi_prompt(page)
    await page.wait_for_selector('[role="navigation"], [aria-label="Mail"]', timeout=60000)


async def _automated_login(service: Optional[str], identity: Optional[str], state_path: Optional[Path]) -> bool:
    """Attempt a fully headless login when credentials are configured."""

    if not service or not state_path:
        return False

    if _BROWSER is None:
        return False

    creds = _credentials_for(service, identity)
    if not creds:
        return False

    username, password = creds
    url = SERVICE_URLS.get(service)
    if not url:
        return False

    login_context = await _BROWSER.new_context(**_base_context_kwargs())
    page = None
    try:
        await apply_stealth(login_context)
        page = await login_context.new_page()
        await page.goto(url, wait_until="load", timeout=60000)

        if service == "outlook":
            # Some tenants immediately redirect to a custom ADFS login (e.g. NWU).
            adfs_used = await _try_nwu_adfs_login(page, username, password)

            if not adfs_used:
                await page.wait_for_selector('input[name="loginfmt"]', timeout=30000)
                await page.fill('input[name="loginfmt"]', username)
                await page.click('input[type="submit"]#idSIButton9')

                try:
                    await page.wait_for_selector('input[name="passwd"]', timeout=20000)
                except PWTimeout:
                    adfs_used = await _try_nwu_adfs_login(page, username, password)
                else:
                    await page.fill('input[name="passwd"]', password)
                    await page.click('input[type="submit"]#idSIButton9')

            if adfs_used:
                # Some ADFS flows still bounce back to Microsoft for the final password prompt.
                try:
                    await page.wait_for_selector('input[name="passwd"]', timeout=5000)
                except PWTimeout:
                    pass
                else:
                    await page.fill('input[name="passwd"]', password)
                    await page.click('input[type="submit"]#idSIButton9')

            await _wait_for_outlook_ready(page)
        elif service == "onedrive":
            await page.wait_for_selector('input[name="loginfmt"]', timeout=30000)
            await page.fill('input[name="loginfmt"]', username)
            await page.click('input[type="submit"]#idSIButton9')

            await page.wait_for_selector('input[name="passwd"]', timeout=30000)
            await page.fill('input[name="passwd"]', password)
            await page.click('input[type="submit"]#idSIButton9')

            try:
                await page.wait_for_selector('input[id="idBtn_Back"]', timeout=5000)
                await page.click('input[id="idBtn_Back"]')
            except PWTimeout:
                pass

            await page.wait_for_selector('[role="main"], [data-automationid="TopBar"]', timeout=60000)
        elif service == "drive":
            await page.wait_for_selector('input[type="email"]', timeout=30000)
            await page.fill('input[type="email"]', username)
            await page.click('#identifierNext')

            await page.wait_for_selector('input[type="password"]', timeout=30000)
            await page.fill('input[type="password"]', password)
            await page.click('#passwordNext')

            await page.wait_for_selector('[role="main"], [data-id="my-drive"]', timeout=60000)
        else:
            logger.debug("Automated login not implemented for %s", service)
            return False

        state_path.parent.mkdir(parents=True, exist_ok=True)
        await login_context.storage_state(path=str(state_path))
        logger.info("Captured %s storage state automatically (headless).", service)
        return True
    except Exception as exc:
        logger.error("Automated login for %s failed: %s", service, exc)
        return False
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        try:
            await login_context.close()
        except Exception:
            pass


async def _prompt_manual_login(context: Any, service: str, state_path: Path, identity: Optional[str]) -> None:
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
        "Storage state for %s (%s) not found. A visible Chromium window has been opened for manual login.",
        service,
        identity or "default",
    )
    prompt = (
        f"Complete the {service} sign-in flow for {identity or 'this account'} in the opened Chromium window.\n"
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


async def _ensure_storage_state(service: Optional[str], state_path: Optional[Path], identity: Optional[str]) -> None:
    """Ensure a storage_state file exists; trigger interactive capture if necessary."""

    if not service or not state_path:
        return

    if state_path.exists():
        return

    try:
        automated = await _automated_login(service, identity, state_path)
    except Exception as exc:
        logger.error("Automated login attempt for %s crashed: %s", service, exc)
        automated = False

    if automated and state_path.exists():
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
        await _prompt_manual_login(login_context, service, state_path, identity)
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

def _clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


async def _soft_scroll(page: Any, times: int = 5, delay: int = 500) -> None:
    """Smooth scroll to trigger lazy loading using multiple strategies."""
    for _ in range(times):
        try:
            await page.mouse.wheel(0, 600)
        except Exception:
            try:
                await page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
            except Exception:
                pass
        try:
            await page.keyboard.press("PageDown")
        except Exception:
            pass
        await page.wait_for_timeout(delay)


async def _query_with_fallbacks(node: Any, selectors: List[str], attribute: Optional[str] = None) -> str:
    for sel in selectors:
        try:
            handle = await node.query_selector(sel)
        except Exception:
            handle = None
        if not handle:
            continue
        try:
            if attribute:
                value = await handle.get_attribute(attribute)
            else:
                value = await handle.inner_text()
        except Exception:
            value = ""
        text = _clean_text(value)
        if text:
            return text
    return ""

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

async def _ocr_element_text(element: Any) -> str:
    """Attempt OCR-based text extraction from an element screenshot."""
    if not OCR_AVAILABLE or element is None:
        return ""

    try:
        data = await element.screenshot(type="png")
    except Exception as exc:
        logger.debug("Element screenshot failed for OCR: %s", exc)
        return ""

    try:
        with Image.open(io.BytesIO(data)) as img:  # type: ignore[arg-type]
            text = pytesseract.image_to_string(img, config="--psm 6")  # type: ignore[union-attr]
    except Exception as exc:
        logger.debug("OCR text extraction failed: %s", exc)
        return ""

    return _clean_text(text)


async def _extract_element_text(node: Any, selector: str, timeout: int = 5000, allow_ocr: bool = True) -> str:
    """Extract text from first matching element with optional OCR fallback."""
    element = None
    try:
        await node.wait_for_selector(selector, timeout=timeout)
        element = await node.query_selector(selector)
    except Exception:
        element = None

    if not element:
        return ""

    try:
        text = await element.inner_text()
    except Exception:
        text = ""

    cleaned = _clean_text(text)
    if cleaned:
        return cleaned

    if allow_ocr:
        return await _ocr_element_text(element)

    return ""

# --------------------------------------------------------------------------------------
# Scrapers
# --------------------------------------------------------------------------------------

async def scrape_outlook(page: Any, month_bounds: Optional[Tuple[dt.date, dt.date]] = None) -> List[Dict[str, Any]]:
    """Outlook scraper with deep read and month filtering."""
    items: List[Dict[str, Any]] = []

    try:
        await page.wait_for_selector('[role="listitem"], div[role="option"]', timeout=20000)
    except Exception:
        logger.warning("Outlook message list not detected in expected time; continuing with best-effort scrape")

    await _soft_scroll(page, times=25, delay=350)

    row_selectors = [
        '[role="listitem"][data-convid]',
        '[role="listitem"][data-conversation-id]',
        '[aria-label*="Message list"] [role="listitem"]',
        'div[role="option"]',
    ]

    rows: List[Any] = []
    for sel in row_selectors:
        nodes = await page.query_selector_all(sel)
        if nodes:
            rows = nodes
            break

    if not rows:
        rows = await page.query_selector_all('[role="listitem"]')

    if not rows:
        logger.warning("No Outlook rows located; returning empty result set")
        return items

    for idx, row in enumerate(rows):
        if len(items) >= 300:
            break

        try:
            await row.scroll_into_view_if_needed()
        except Exception:
            try:
                await row.evaluate("node => node.scrollIntoView({block: 'center', inline: 'nearest'})")
            except Exception:
                pass

        meta: Dict[str, Any] = {}
        try:
            meta = await row.evaluate(
                """
                (node) => {
                    const getText = (selectors) => {
                        for (const sel of selectors) {
                            const target = node.querySelector(sel);
                            if (target && target.textContent) {
                                return target.textContent.trim();
                            }
                        }
                        return "";
                    };

                    const attr = (name) => node.getAttribute(name) || "";

                    return {
                        subject: getText([
                            '[data-test-id="message-subject"]',
                            '[role="heading"]',
                            'span[title]',
                            '.ms-ListItem-primaryText',
                            '.KxTitle'
                        ]),
                        sender: getText([
                            '[data-test-id="sender"]',
                            'span[title][id*="sender"]',
                            '.ms-Persona-primaryText',
                            'span[aria-label*="From"]',
                            '.KxFrom'
                        ]),
                        preview: getText([
                            '[data-test-id="message-preview"]',
                            '.messagePreview',
                            '.ms-ListItem-tertiaryText',
                            '.KxPreview'
                        ]),
                        when: getText([
                            '[data-test-id="message-received"]',
                            'time',
                            'span[aria-label*="AM"]',
                            'span[aria-label*="PM"]',
                            'span[title*="202"]',
                            'span[title*="20"]'
                        ]) || attr('data-converteddatetime') || attr('data-timestamp'),
                        aria: attr('aria-label'),
                        convoId: attr('data-convid') || attr('data-conversation-id') || attr('data-conversationid') || attr('data-unique-id'),
                        nodeText: node.innerText || ""
                    };
                }
                """
            )
        except Exception as exc:
            logger.debug("Outlook row metadata evaluation failed: %s", exc)

        subject = _clean_text(meta.get("subject")) if meta else ""
        sender = _clean_text(meta.get("sender")) if meta else ""
        preview = _clean_text(meta.get("preview")) if meta else ""
        ts_text = _clean_text(meta.get("when")) if meta else ""
        aria_label = _clean_text(meta.get("aria")) if meta else ""
        convo_id = _clean_text(meta.get("convoId")) if meta else ""
        node_text = _clean_text(meta.get("nodeText")) if meta else ""
        if not node_text:
            try:
                direct_text = await row.inner_text()
            except Exception:
                direct_text = ""
            node_text = _clean_text(direct_text)
        if not node_text:
            node_text = await _ocr_element_text(row)

        if node_text:
            parts = [p.strip() for p in node_text.split("\n") if p.strip()]
        else:
            parts = []

        if not sender and parts:
            sender = parts[0]
        if not subject and len(parts) > 1:
            subject = parts[1]
        if not ts_text and parts:
            for candidate in reversed(parts):
                if any(char.isdigit() for char in candidate):
                    ts_text = candidate
                    break

        if not subject:
            subject = "(no subject)"
        if not sender:
            sender = "(unknown sender)"

        ts = _parse_ts(ts_text) if ts_text else None

        if ts and not _in_month(ts, month_bounds):
            continue

        try:
            await row.hover()
        except Exception:
            pass

        opened = False
        try:
            await row.click(timeout=3000)
            opened = True
        except Exception:
            try:
                await row.focus()
                await page.keyboard.press("Enter")
                opened = True
            except Exception:
                logger.debug("Unable to activate Outlook row for %s", subject)

        if opened:
            await page.wait_for_timeout(600)

        body_text = await _extract_element_text(page, 'div[role="document"]', timeout=4000)
        if not body_text:
            body_text = await _extract_element_text(page, '[aria-label*="Message body"]', timeout=3000)
        if not body_text:
            handle = await page.query_selector('div[role="document"]')
            if handle:
                body_text = await _ocr_element_text(handle)
        if not body_text:
            handle = await page.query_selector('[aria-label*="Message body"]')
            if handle:
                body_text = await _ocr_element_text(handle)
        body_text = _clean_text(body_text)

        timestamp_value = ts.isoformat() if ts else _now_iso()

        path_id = convo_id or f"{sender} - {subject}"
        item = {
            "source": "outlook",
            "path": path_id,
            "title": subject,
            "sender": sender,
            "size": 0,
            "timestamp": timestamp_value,
        }

        if ts_text:
            item["raw_timestamp"] = ts_text
        if aria_label:
            item["aria_label"] = aria_label
        if preview:
            item["preview"] = preview
        if body_text:
            item["body"] = body_text

        item["hash"] = _hash_from(item["source"], item["path"], item.get("timestamp", ""))

        items.append(item)

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
            try:
                raw_text = await el.inner_text()
            except Exception:
                raw_text = ""
            txt = _clean_text(raw_text)
            if (not txt or len(txt) < 5) and OCR_AVAILABLE:
                txt = await _ocr_element_text(el)
            if not txt or len(txt) < 5:
                continue
            first = (txt.split("\n")[0] or "")[0:160].strip()
            if not first:
                continue
            ts_text = await _extract_element_text(el, 'time, .date', timeout=2000)
            if not ts_text:
                ts_text = await _extract_element_text(page, 'time, .date', timeout=3000, allow_ocr=False)
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

async def run_scan_active(url: str, on_progress: Optional[Callable] = None, month_bounds: Optional[Tuple[dt.date, dt.date]] = None, identity: Optional[str] = None) -> List[Dict[str, Any]]:
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
            context = await get_authenticated_context(service, identity)
        else:
            context = await get_authenticated_context(service or "generic", identity)
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

    logger.info("Scraped %d %s items from %s", len(items), service or "unknown", url)

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

if OCR_AVAILABLE:
    logger.info("OCR fallback enabled for scraper text extraction")
else:
    if _OCR_ERROR:
        logger.info("OCR fallback disabled: %s", _OCR_ERROR)
    else:
        logger.info("OCR fallback disabled: dependencies not installed")

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

    return await run_scan_active(url=url, month_bounds=month_bounds, on_progress=progress_callback, identity=email)
