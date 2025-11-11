from __future__ import annotations

import os
import re
from textwrap import dedent
from typing import Any, Dict, List

from playwright.async_api import async_playwright

try:
    from .outlook_selectors import OUTLOOK_ROW_SELECTORS
except ImportError:  # pragma: no cover - legacy entrypoint support
    from outlook_selectors import OUTLOOK_ROW_SELECTORS  # type: ignore

OUTLOOK_MAX_ROWS = int(os.getenv("VAMP_OUTLOOK_MAX_ROWS", "500"))
OUTLOOK_RETRY_WAIT_MS = int(os.getenv("VAMP_OUTLOOK_RETRY_WAIT_MS", "1500"))


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip() if text else ""

def clean_text(html: str) -> str:
    # Simple normalization: remove excessive whitespace and strip tags
    text = re.sub(r'<[^>]+>', '', html)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

async def try_click_and_extract(page, selector, extract_func, retries=3):
    for attempt in range(retries):
        try:
            await page.wait_for_selector(selector, timeout=5000)
            element = await page.query_selector(selector)
            return await extract_func(element)
        except Exception:
            if attempt == retries - 1:
                return "(Failed to extract after retries)"
            await page.wait_for_timeout(1000)
    return "(Retry exhausted)"

async def _soft_scroll(page, times: int = 20, delay: int = 250) -> None:
    for _ in range(times):
        try:
            await page.mouse.wheel(0, 600)
        except Exception:
            try:
                await page.evaluate("window.scrollBy(0, window.innerHeight / 2)")
            except Exception:
                pass
        await page.wait_for_timeout(delay)


async def _extract_row_meta(row: Any) -> Dict[str, str]:
    try:
        return await row.evaluate(
            dedent(
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
                        text: node.innerText || ""
                    };
                }
                """
            )
        )
    except Exception:
        return {}


async def _wait_for_preview_content(page: Any, timeout: int = 6000) -> bool:
    try:
        await page.wait_for_function(
            dedent(
                """
                () => {
                    const doc = document.querySelector("div[role='document']")
                        || document.querySelector("[aria-label*='Message body']");
                    return doc && doc.innerText && doc.innerText.trim().length > 0;
                }
                """
            ),
            timeout=timeout,
        )
        return True
    except Exception:
        return False


async def scrape_outlook(page) -> List[Dict]:
    await page.wait_for_load_state("networkidle")
    results: List[Dict] = []
    seen: set[str] = set()

    await _soft_scroll(page, times=15)

    rows: List[Any] = []
    selector_hits: List[tuple[str, int]] = []

    for attempt in range(3):
        rows = []
        selector_hits.clear()
        for selector in OUTLOOK_ROW_SELECTORS:
            try:
                nodes = await page.query_selector_all(selector)
            except Exception:
                nodes = []
            if not nodes:
                continue
            selector_hits.append((selector, len(nodes)))
            rows.extend(nodes)

        if rows:
            break

        await _soft_scroll(page, times=10 + attempt * 5)
        await page.wait_for_timeout(OUTLOOK_RETRY_WAIT_MS)

    if not rows:
        rows = await page.query_selector_all("div[role='listitem']")

    for idx, item in enumerate(rows):
        if len(results) >= OUTLOOK_MAX_ROWS:
            break

        meta = await _extract_row_meta(item)
        subject = _squash(meta.get("subject", "")) or "(no subject)"
        sender = _squash(meta.get("sender", "")) or "(unknown sender)"
        preview = _squash(meta.get("preview", ""))
        when = _squash(meta.get("when", ""))
        aria = _squash(meta.get("aria", ""))
        convo_id = _squash(meta.get("convoId", "")) or f"outlook_{idx}"

        text_blob = _squash(meta.get("text", ""))
        if not preview and text_blob:
            preview = text_blob

        dedup_key = "::".join([
            convo_id.lower(),
            subject.lower(),
            sender.lower(),
            when.lower(),
        ])
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        try:
            await item.scroll_into_view_if_needed()
        except Exception:
            try:
                await item.evaluate("node => node.scrollIntoView({block: 'center', inline: 'nearest'})")
            except Exception:
                pass

        body = ""
        try:
            await item.click(timeout=4000)
            ready = await _wait_for_preview_content(page)
            if not ready:
                await page.wait_for_timeout(500)
            html = await try_click_and_extract(page, "div[role='document']", lambda el: el.inner_html())
            body = clean_text(html)
            if not body:
                alt_html = await try_click_and_extract(
                    page,
                    "[aria-label*='Message body']",
                    lambda el: el.inner_html(),
                )
                body = clean_text(alt_html)
        except Exception as e:
            results.append({
                "id": f"outlook_error_{idx}",
                "type": "error",
                "content": str(e)
            })
            continue

        payload: Dict[str, Any] = {
            "id": convo_id,
            "type": "email",
            "subject": subject,
            "sender": sender,
            "raw_timestamp": when,
            "aria_label": aria,
            "preview": preview,
            "content": body or preview,
        }
        results.append(payload)

    return results

async def scrape_generic_iframe(page, label) -> List[Dict]:
    await page.wait_for_load_state("networkidle")
    results = []
    items = await page.query_selector_all("div[role='row'], div[role='listitem'], tr")
    for idx, item in enumerate(items[:3]):
        try:
            await item.click()
            await page.wait_for_timeout(3000)
            iframe = await page.query_selector("iframe")
            content = "(No iframe found)"
            if iframe:
                frame = await iframe.content_frame()
                html = await frame.content() if frame else "(No content)"
                content = clean_text(html)
            results.append({"id": f"{label}_{idx}", "type": f"{label}_preview", "content": content})
        except Exception as e:
            results.append({"id": f"{label}_error_{idx}", "type": "error", "content": str(e)})
    return results

async def scrape_onedrive(page): return await scrape_generic_iframe(page, "onedrive")
async def scrape_google_drive(page): return await scrape_generic_iframe(page, "gdrive")
async def scrape_nextcloud(page): return await scrape_generic_iframe(page, "nextcloud")

async def scrape_efundi(page) -> List[Dict]:
    await page.wait_for_load_state("networkidle")
    results = []
    panels = await page.query_selector_all(".portletBody")
    for idx, panel in enumerate(panels[:3]):
        try:
            text = await panel.inner_text()
            results.append({"id": f"efundi_{idx}", "type": "section", "content": clean_text(text)})
        except Exception as e:
            results.append({"id": f"efundi_error_{idx}", "type": "error", "content": str(e)})
    return results

async def run_full_deep_scan(url: str) -> List[Dict]:
    user_data_dir = "C:\\Users\\User\\AppData\\Local\\Google\\Chrome\\User Data"
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(user_data_dir=user_data_dir, headless=False)
        page = await browser.new_page()
        await page.goto(url, timeout=60000)

        if "outlook" in url:
            results = await scrape_outlook(page)
        elif "onedrive" in url:
            results = await scrape_onedrive(page)
        elif "drive.google" in url:
            results = await scrape_google_drive(page)
        elif "nextcloud" in url:
            results = await scrape_nextcloud(page)
        elif "efundi" in url:
            results = await scrape_efundi(page)
        else:
            content = await page.content()
            results = [{"id": "generic", "type": "html_dump", "content": clean_text(content)}]

        await browser.close()
        return results
