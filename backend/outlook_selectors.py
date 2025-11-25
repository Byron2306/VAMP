"""Shared Outlook selector definitions used by frontend and backend scrapers."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

_BASE_DIR = Path(__file__).resolve().parent
_SHARED_JSON = _BASE_DIR.parent / "frontend" / "extension" / "shared" / "outlook_selectors.json"

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

_DEFAULT_SELECTORS: List[str] = list(dict.fromkeys(
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
def load_outlook_selectors() -> List[str]:
    """Return the canonical list of Outlook row selectors.

    The selectors are stored in a JSON file that is bundled with both the
    browser extension and the backend so that changes stay in lockstep.  The
    JSON is cached to avoid repeatedly touching the filesystem during long
    scraping sessions.  If the JSON is unavailable, we fall back to a
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

    return list(_DEFAULT_SELECTORS)


# Export a module level constant for convenience while keeping the loader
# available for tests.
OUTLOOK_ROW_SELECTORS: List[str] = load_outlook_selectors()

__all__ = [
    "OUTLOOK_ROW_SELECTORS",
    "OUTLOOK_ROW_FALLBACKS",
    "OUTLOOK_SELECTOR_SETS",
    "load_outlook_selectors",
]
