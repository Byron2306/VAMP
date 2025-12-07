"""Compatibility shim that delegates to :mod:`backend.vamp_agent`."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .vamp_agent import (  # re-exported for legacy imports
    apply_stealth,
    ensure_browser,
    get_authenticated_context,
    run_scan_active,
    run_scan_active_ws,
    scrape_drive,
    scrape_efundi,
    scrape_onedrive,
    scrape_outlook,
)

__all__ = [
    "apply_stealth",
    "ensure_browser",
    "get_authenticated_context",
    "run_scan_active",
    "run_scan_active_ws",
    "scrape_drive",
    "scrape_efundi",
    "scrape_onedrive",
    "scrape_outlook",
    "get_or_create_browser_context",
]


async def _page_has_any_selector(page: Any, selectors: List[str], timeout: int = 2000) -> bool:
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=timeout)
            return True
        except Exception:
            continue
    return False


async def get_or_create_browser_context(
    storage_path: str,
    login_url: str,
    ready_selectors: List[str],
    *,
    login_indicators: Optional[List[str]] = None,
    timeout: int = 300,
) -> Any:
    """Create or reuse a browser context with manual login support.

    If ``storage_path`` exists the cookies/session are loaded. Otherwise the
    user is guided through a manual login flow; once ``ready_selectors`` are
    visible the storage state is persisted for future runs.
    """

    await ensure_browser()
    from . import vamp_agent as _va  # Local import to avoid cycles

    browser = getattr(_va, "_BROWSER", None)
    if browser is None:
        raise RuntimeError("Browser failed to launch; Playwright may be missing or blocked")

    state_file = Path(storage_path) if storage_path else None
    context_kwargs = _va._base_context_kwargs()  # type: ignore[attr-defined]
    if state_file and state_file.exists():
        context_kwargs["storage_state"] = str(state_file)

    context = await browser.new_context(**context_kwargs)
    await apply_stealth(context)

    page = await context.new_page()
    await page.goto(login_url, timeout=60000)

    ready_indicators = list(ready_selectors)
    login_indicators = login_indicators or [
        "button:has-text('Sign in')",
        "input[type=\"email\"]",
        "input[name=\"loginfmt\"]",
    ]

    if await _page_has_any_selector(page, ready_indicators, timeout=3000):
        if state_file:
            await context.storage_state(path=str(state_file))
        return context

    deadline = time.time() + timeout
    last_ping = 0.0
    try:
        while time.time() < deadline:
            if await _page_has_any_selector(page, ready_indicators, timeout=2000):
                if state_file:
                    await context.storage_state(path=str(state_file))
                return context

            if await _page_has_any_selector(page, login_indicators, timeout=1500):
                # Still on login form; keep waiting
                pass

            if time.time() - last_ping > 30:
                last_ping = time.time()
            await page.wait_for_timeout(1000)
    except Exception as exc:
        await context.close()
        raise RuntimeError(f"Browser context error: {exc}") from exc

    await context.close()
    raise RuntimeError("Login required / timed out before selectors became visible")


async def run_scan_active_compat(*args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    """Backwards compatible coroutine for callers expecting the legacy module."""

    return await run_scan_active(*args, **kwargs)


def run_scan_active_sync(*args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
    """Synchronously execute :func:`run_scan_active` for legacy scripts."""

    import asyncio

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(run_scan_active(*args, **kwargs))
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        asyncio.set_event_loop(None)
        loop.close()


__legacy__: Dict[str, Callable[..., Awaitable[Any]]] = {
    "run_scan_active": run_scan_active_compat,
}

