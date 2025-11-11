"""Google Drive connector stub managed by the agent."""

from __future__ import annotations

import logging
from typing import Dict, Iterable

from ..agent_app.plugin_manager import PlatformConnector
from ..vamp_agent import SERVICE_URLS

logger = logging.getLogger(__name__)


class GoogleDriveConnector(PlatformConnector):
    name = "drive"
    description = "Google Drive evidence ingestion"
    supports_oauth = True

    def diagnostics(self) -> Dict[str, object]:
        return {
            "status": "ready" if self.config.get("enabled", True) else "disabled",
            "supports_oauth": self.supports_oauth,
            "portal": SERVICE_URLS.get("drive"),
            "config": self.config,
        }

    def required_scopes(self) -> Iterable[str]:
        return ["openid", "https://www.googleapis.com/auth/drive.readonly"]

    def connect(self, **kwargs) -> None:
        logger.debug("Google Drive connector invoked with %s", kwargs)


__all__ = ["GoogleDriveConnector"]
