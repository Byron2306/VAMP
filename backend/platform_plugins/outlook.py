"""Outlook connector managed as an agent plugin."""

from __future__ import annotations

import logging
from typing import Dict, Iterable

from ..agent_app.plugin_manager import PlatformConnector
from ..vamp_agent import SERVICE_URLS

logger = logging.getLogger(__name__)


class OutlookConnector(PlatformConnector):
    name = "outlook"
    description = "Office365 Outlook webmail automation"
    supports_oauth = True

    def diagnostics(self) -> Dict[str, object]:
        return {
            "status": "ready",
            "supports_oauth": self.supports_oauth,
            "portal": SERVICE_URLS.get("outlook"),
        }

    def required_scopes(self) -> Iterable[str]:
        return ["offline_access", "Mail.Read"]

    def connect(self, **kwargs) -> None:
        logger.debug("Outlook connector invoked with %s", kwargs)


__all__ = ["OutlookConnector"]
