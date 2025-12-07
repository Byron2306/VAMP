"""Selector smoke tests for Outlook and OneDrive Playwright scrapers.

Run this after signing in once (so storage_state is available):

```
python tools/selector_smoke_test.py --service outlook
python tools/selector_smoke_test.py --service onedrive
```
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import List

from backend.outlook_selectors import OUTLOOK_SELECTORS
from backend.onedrive_selectors import ONEDRIVE_SELECTORS
from backend.vamp_agent import SERVICE_URLS, get_authenticated_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("selector_smoke_test")


async def _first_match(page, selectors: List[str]):
    for selector in selectors:
        try:
            handle = await page.query_selector(selector)
        except Exception:
            handle = None
        if handle:
            return selector, handle
    return None, None


async def check_outlook(url: str, identity: str | None) -> None:
    context = await get_authenticated_context("outlook", identity)
    page = await context.new_page()
    await page.goto(url, timeout=60000)

    selector, handle = await _first_match(page, OUTLOOK_SELECTORS.inbox_list)
    if handle:
        logger.info("Inbox list located via %s", selector)
    else:
        logger.error("Inbox list not found via known selectors")

    rows = []
    for sel in OUTLOOK_SELECTORS.message_row:
        try:
            rows = await page.query_selector_all(sel)
        except Exception:
            rows = []
        if rows:
            logger.info("Found %d message rows via %s", len(rows), sel)
            break
    if not rows:
        logger.error("No message rows found with configured selectors")
        await page.close()
        return

    first_row = rows[0]
    subject = await first_row.inner_text()
    logger.info("First row text snippet: %s", (subject or "").strip()[:80])

    await first_row.click(timeout=5000)
    attach_selector, attach_node = await _first_match(page, OUTLOOK_SELECTORS.attachment_item)
    if attach_node:
        logger.info("Attachment area detected via %s", attach_selector)
    else:
        logger.info("Attachment area not detected on first message (may be absent)")

    await page.close()


async def check_onedrive(url: str, identity: str | None) -> None:
    context = await get_authenticated_context("onedrive", identity)
    page = await context.new_page()
    await page.goto(url, timeout=60000)

    selector, handle = await _first_match(page, ONEDRIVE_SELECTORS.grid)
    if handle:
        logger.info("Grid located via %s", selector)
    else:
        logger.error("Grid not located; OneDrive layout may have changed")

    rows = []
    for sel in ONEDRIVE_SELECTORS.row:
        try:
            rows = await page.query_selector_all(sel)
        except Exception:
            rows = []
        if rows:
            logger.info("Found %d rows via %s", len(rows), sel)
            break
    if not rows:
        logger.error("No rows detected with configured selectors")
    else:
        first = rows[0]
        name = await first.inner_text()
        logger.info("First row text snippet: %s", (name or "").strip()[:80])

    await page.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Selector smoke test harness")
    parser.add_argument("--service", choices=["outlook", "onedrive"], default="outlook")
    parser.add_argument("--url", help="Override URL", default=None)
    parser.add_argument("--identity", help="Storage identity/email", default=None)
    args = parser.parse_args()

    url = args.url or SERVICE_URLS.get(args.service)
    if not url:
        raise SystemExit(f"No default URL known for service {args.service}")

    if args.service == "outlook":
        await check_outlook(url, args.identity)
    else:
        await check_onedrive(url, args.identity)


if __name__ == "__main__":
    asyncio.run(main())
