"""Dynamic plugin loader for platform connectors."""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Type

from . import AGENT_CONFIG_DIR

logger = logging.getLogger(__name__)

CONFIG_FILE = AGENT_CONFIG_DIR / "platform_config.json"


@dataclass
class PluginDefinition:
    name: str
    module: str
    cls: str
    enabled: bool = True
    config: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "module": self.module,
            "cls": self.cls,
            "enabled": self.enabled,
            "config": self.config,
        }


class PlatformConnector:
    """Base connector interface all plugins must implement."""

    name: str = ""
    description: str = ""
    supports_oauth: bool = False

    def __init__(self, config: Optional[Dict[str, object]] = None) -> None:
        self.config = config or {}

    def diagnostics(self) -> Dict[str, object]:  # pragma: no cover - interface
        return {"status": "unknown"}

    def required_scopes(self) -> Iterable[str]:  # pragma: no cover - interface
        return []

    def connect(self, **kwargs) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class PluginManager:
    def __init__(self, config_file: Path = CONFIG_FILE) -> None:
        self.config_file = config_file
        self._definitions: Dict[str, PluginDefinition] = {}
        self._instances: Dict[str, PlatformConnector] = {}
        self._load_config()

    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        if not self.config_file.exists():
            self._write_default()
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Unable to load connector config: %s", exc)
            data = {"connectors": []}
        items = data.get("connectors", []) if isinstance(data, dict) else []
        definitions: Dict[str, PluginDefinition] = {}
        for raw in items:
            try:
                definition = PluginDefinition(
                    name=str(raw["name"]),
                    module=str(raw["module"]),
                    cls=str(raw["class"] if "class" in raw else raw["cls"]),
                    enabled=bool(raw.get("enabled", True)),
                    config=dict(raw.get("config", {})),
                )
            except Exception as exc:
                logger.warning("Invalid connector definition %s: %s", raw, exc)
                continue
            definitions[definition.name] = definition
        self._definitions = definitions

    def _write_default(self) -> None:
        default = {
            "connectors": [
                {
                    "name": "outlook",
                    "module": "backend.platform_plugins.outlook",
                    "cls": "OutlookConnector",
                    "enabled": True,
                    "config": {},
                },
                {
                    "name": "onedrive",
                    "module": "backend.platform_plugins.onedrive",
                    "cls": "OneDriveConnector",
                    "enabled": False,
                    "config": {},
                },
                {
                    "name": "drive",
                    "module": "backend.platform_plugins.drive",
                    "cls": "GoogleDriveConnector",
                    "enabled": False,
                    "config": {},
                },
            ]
        }
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(json.dumps(default, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    def _load_class(self, definition: PluginDefinition) -> Type[PlatformConnector]:
        module = importlib.import_module(definition.module)
        cls_name = definition.cls
        try:
            return getattr(module, cls_name)
        except AttributeError as exc:
            raise ImportError(f"Connector class {cls_name} not found in {definition.module}") from exc

    def get_connector(self, name: str, *, reload: bool = False) -> Optional[PlatformConnector]:
        definition = self._definitions.get(name)
        if not definition or not definition.enabled:
            return None
        if not reload and name in self._instances:
            return self._instances[name]
        try:
            cls = self._load_class(definition)
        except Exception as exc:
            logger.error("Failed to load connector %s: %s", name, exc)
            return None
        instance = cls(definition.config)
        self._instances[name] = instance
        return instance

    def connectors(self, include_disabled: bool = False) -> List[PluginDefinition]:
        if include_disabled:
            return list(self._definitions.values())
        return [definition for definition in self._definitions.values() if definition.enabled]

    def enable(self, name: str) -> None:
        if name not in self._definitions:
            raise KeyError(name)
        definition = self._definitions[name]
        definition.enabled = True
        self._instances.pop(name, None)
        self._persist()

    def disable(self, name: str) -> None:
        if name not in self._definitions:
            raise KeyError(name)
        definition = self._definitions[name]
        definition.enabled = False
        self._instances.pop(name, None)
        self._persist()

    def update_config(self, name: str, config: Dict[str, object]) -> None:
        if name not in self._definitions:
            raise KeyError(name)
        definition = self._definitions[name]
        definition.config = config
        self._instances.pop(name, None)
        self._persist()

    def add_connector(self, definition: PluginDefinition) -> None:
        self._definitions[definition.name] = definition
        self._persist()

    def remove_connector(self, name: str) -> None:
        if name in self._definitions:
            del self._definitions[name]
            self._instances.pop(name, None)
            self._persist()

    def _persist(self) -> None:
        payload = {"connectors": [definition.to_dict() for definition in self._definitions.values()]}
        self.config_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def default(cls) -> "PluginManager":
        return cls()


__all__ = ["PluginManager", "PlatformConnector", "PluginDefinition", "CONFIG_FILE"]
