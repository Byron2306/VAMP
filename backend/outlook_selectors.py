"""Shared Outlook selector definitions used by frontend and backend scrapers.

Selectors verified against Outlook Web as of 2025-05. If Outlook UI changes,
update this module instead of scattering ad-hoc selectors across scrapers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

_BASE_DIR = Path(__file__).resolve().parent
_SHARED_JSON = _BASE_DIR.parent / "frontend" / "extension" / "shared" / "outlook_selectors.json"


@dataclass(frozen=True)
class OutlookSelectorConfig:
    inbox_list: List[str]
    message_row: List[str]
    message_subject: List[str]
    message_sender: List[str]
    message_preview: List[str]
    message_date: List[str]
    message_open: List[str]
    attachment_list: List[str]
    attachment_item: List[str]
    attachment_name: List[str]
    body: List[str]


OUTLOOK_SELECTOR_SETS: Dict[str, Dict[str, str]] = {
    "v2024_q4": {
        "message_list": '[data-test-id="message-list"]',
        "message_row": '[role="listitem"][data-convid]',
        "subject": '[data-test-id="message-subject"]',
    },
    "v2024_q3": {
        "message_list": ".ms-List",
        "message_row": ".ms-ListItem",
        "subject": ".ms-ListItem-primaryText",
    },
}

OUTLOOK_ROW_FALLBACKS: List[str] = [
    OUTLOOK_SELECTOR_SETS["v2024_q4"]["message_row"],
    OUTLOOK_SELECTOR_SETS["v2024_q3"]["message_row"],
    "div[role=\"listitem\"]",
]

_DEFAULT_ROW_SELECTORS: List[str] = list(dict.fromkeys(
    OUTLOOK_ROW_FALLBACKS
    + [
        "[data-convid]",
        "[data-conversation-id]",
        "[data-conversationid]",
        "[data-item-id]",
        "[aria-label*=\"Message list\"] [role=\"listitem\"]",
        "[data-automation-id=\"messageList\"] [role=\"option\"]",
        "[data-tid=\"messageListContainer\"] [role=\"option\"]",
        "[data-app-section=\"Mail\"] [role=\"treeitem\"]",
        "[role=\"option\"][data-convid]",
        "[role=\"option\"][data-item-id]",
    ]
))


@lru_cache(maxsize=1)
def load_outlook_row_selectors() -> List[str]:
    """Return the canonical list of Outlook row selectors.

    The selectors are stored in a JSON file that is bundled with both the
    browser extension and the backend so that changes stay in lockstep. The
    JSON is cached to avoid repeatedly touching the filesystem during long
    scraping sessions. If the JSON is unavailable, we fall back to a
    versioned selector matrix that prioritizes the latest Outlook UI updates
    while keeping legacy selectors for older layouts.
    """

    try:
        data = json.loads(_SHARED_JSON.read_text(encoding="utf-8"))
        if isinstance(data, list):
            cleaned = [s for s in (str(x).strip() for x in data) if s]
            if cleaned:
                return cleaned
    except FileNotFoundError:
        pass
    except Exception:
        # Fall back to the baked-in defaults if anything goes wrong.
        pass

    return list(_DEFAULT_ROW_SELECTORS)


def _default_config() -> OutlookSelectorConfig:
    row_selectors = load_outlook_row_selectors()
    return OutlookSelectorConfig(
        inbox_list=[
            OUTLOOK_SELECTOR_SETS["v2024_q4"]["message_list"],
            '[aria-label*="Message list"]',
            "[role='list'][data-convid]",
        ],
        message_row=row_selectors,
        message_subject=[
            OUTLOOK_SELECTOR_SETS["v2024_q4"]["subject"],
            OUTLOOK_SELECTOR_SETS["v2024_q3"]["subject"],
            "[role='heading']",  # compact list view
        ],
        message_sender=[
            '[data-test-id="message-sender"]',
            '[data-automationid="senders"]',
            '[aria-label*="From"]',
        ],
        message_preview=[
            '[data-test-id="message-preview"]',
            '.messagePreview',
            '.ms-ListItem-tertiaryText',
        ],
        message_date=[
            '[data-test-id="message-received"]',
            'time',
            'span[aria-label*="AM"]',
            'span[aria-label*="PM"]',
            'span[title*="202"]',
        ],
        message_open=[
            '[role="listitem"][data-convid]',
            '[role="option"][data-convid]'
        ],
        attachment_list=[
            'div[role="group"][aria-label*="Attachments"]',
            '[data-test-id="attachment-group"]',
        ],
        attachment_item=[
            '[data-test-id="attachment-card"]',
            '[data-test-id="attachment-preview"]',
            '[data-log-name="Attachment"]',
            'div[role="group"][aria-label*="Attachments"] [role="button"]',
        ],
        attachment_name=[
            '[data-test-id="attachment-name"]',
            'div[role="text"]',
            '[title]',
            'span',
        ],
        body=[
            'div[role="document"]',
            '[aria-label*="Message body"]',
        ],
    )


OUTLOOK_SELECTORS = _default_config()
OUTLOOK_ROW_SELECTORS: List[str] = OUTLOOK_SELECTORS.message_row
ATTACHMENT_CANDIDATES: List[str] = OUTLOOK_SELECTORS.attachment_item
ATTACHMENT_NAME_SELECTORS: List[str] = OUTLOOK_SELECTORS.attachment_name
BODY_SELECTORS: List[str] = OUTLOOK_SELECTORS.body

__all__ = [
    "OUTLOOK_SELECTORS",
    "OUTLOOK_ROW_SELECTORS",
    "OUTLOOK_ROW_FALLBACKS",
    "OUTLOOK_SELECTOR_SETS",
    "OutlookSelectorConfig",
    "load_outlook_row_selectors",
    "ATTACHMENT_CANDIDATES",
    "ATTACHMENT_NAME_SELECTORS",
    "BODY_SELECTORS",
]
