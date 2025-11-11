"""Shared Outlook selector definitions used by frontend and backend scrapers."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import List

_BASE_DIR = Path(__file__).resolve().parent
_SHARED_JSON = _BASE_DIR.parent / "frontend" / "extension" / "shared" / "outlook_selectors.json"

_DEFAULT_SELECTORS: List[str] = [
    "[data-convid]",
    "[data-conversation-id]",
    "[data-conversationid]",
    "[data-item-id]",
    "[role=\"listitem\"][data-convid]",
    "[role=\"listitem\"][data-conversation-id]",
    "[role=\"listitem\"][data-item-id]",
    "[aria-label*=\"Message list\"] [role=\"listitem\"]",
    "[data-automation-id=\"messageList\"] [role=\"option\"]",
    "[data-tid=\"messageListContainer\"] [role=\"option\"]",
    "[data-app-section=\"Mail\"] [role=\"treeitem\"]",
    "[role=\"option\"][data-convid]",
    "[role=\"option\"][data-item-id]",
]


@lru_cache(maxsize=1)
def load_outlook_selectors() -> List[str]:
    """Return the canonical list of Outlook row selectors.

    The selectors are stored in a JSON file that is bundled with both the
    browser extension and the backend so that changes stay in lockstep.  The
    JSON is cached to avoid repeatedly touching the filesystem during long
    scraping sessions.
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

__all__ = ["OUTLOOK_ROW_SELECTORS", "load_outlook_selectors"]
