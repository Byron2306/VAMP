
from playwright.async_api import async_playwright
from typing import List, Dict
import re

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

async def scrape_outlook(page) -> List[Dict]:
    await page.wait_for_load_state("networkidle")
    results = []
    email_items = await page.query_selector_all("div[role='listitem']")
    for idx, item in enumerate(email_items[:3]):
        try:
            await item.click()
            await page.wait_for_timeout(2000)
            html = await try_click_and_extract(page, "div[role='document']", lambda el: el.inner_html())
            results.append({"id": f"outlook_{idx}", "type": "email", "content": clean_text(html)})
        except Exception as e:
            results.append({"id": f"outlook_error_{idx}", "type": "error", "content": str(e)})
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
