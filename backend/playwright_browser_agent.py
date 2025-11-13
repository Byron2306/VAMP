"""Compatibility shim that delegates to :mod:`backend.vamp_agent`."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List

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
]


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

