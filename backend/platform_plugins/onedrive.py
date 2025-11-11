"""OneDrive connector stub managed by the agent."""

from __future__ import annotations

import logging
from typing import Dict, Iterable

from ..agent_app.plugin_manager import PlatformConnector
from ..vamp_agent import SERVICE_URLS

logger = logging.getLogger(__name__)


class OneDriveConnector(PlatformConnector):
    name = "onedrive"
    description = "Microsoft OneDrive evidence ingestion"
    supports_oauth = True

    def diagnostics(self) -> Dict[str, object]:
        enabled = self.config.get("enabled", True)
        return {
            "status": "ready" if enabled else "disabled",
            "supports_oauth": self.supports_oauth,
            "portal": SERVICE_URLS.get("onedrive"),
            "config": self.config,
        }

    def required_scopes(self) -> Iterable[str]:
        return ["offline_access", "Files.Read.All"]

    def connect(self, **kwargs) -> None:
        logger.debug("OneDrive connector invoked with %s", kwargs)


__all__ = ["OneDriveConnector"]
