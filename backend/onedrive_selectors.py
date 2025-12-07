"""Centralised OneDrive selector definitions used by Playwright scrapers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class OneDriveSelectorConfig:
    grid: List[str]
    row: List[str]
    name: List[str]
    modified: List[str]
    open_action: List[str]
    download_action: List[str]


def _default_onedrive_config() -> OneDriveSelectorConfig:
    return OneDriveSelectorConfig(
        grid=[
            '[role="main"] [data-automationid="Grid"]',
            '[data-automationid="TopBar"] ~ div [role="grid"]',
        ],
        row=[
            '[role="row"]',
            '[data-automationid="row"]',
        ],
        name=[
            '[data-automationid="name"]',
            '[aria-label*="Name"]',
        ],
        modified=[
            '[data-automationid="modified"]',
            '[aria-label*="Modified"]',
        ],
        open_action=[
            'button[aria-label*="Open"]',
            'a[role="link"]',
        ],
        download_action=[
            'button[aria-label*="Download"]',
            'button[data-automationid="Download"]',
        ],
    )


ONEDRIVE_SELECTORS = _default_onedrive_config()

__all__ = ["ONEDRIVE_SELECTORS", "OneDriveSelectorConfig"]
