import json
import logging

from backend.agent_app.plugin_manager import PluginManager


def test_duplicate_connectors_warn_and_keep_first(tmp_path, caplog):
    config_file = tmp_path / "platform_config.json"
    config_file.write_text(
        json.dumps(
            {
                "connectors": [
                    {
                        "name": "outlook",
                        "module": "pkg.one",
                        "cls": "ClassA",
                        "enabled": True,
                        "config": {"a": 1},
                    },
                    {
                        "name": "outlook",
                        "module": "pkg.two",
                        "cls": "ClassB",
                        "enabled": False,
                        "config": {"b": 2},
                    },
                    {
                        "name": "drive",
                        "module": "pkg.drive",
                        "cls": "DriveConnector",
                        "enabled": True,
                    },
                ]
            },
            indent=2,
        )
    )

    with caplog.at_level(logging.WARNING):
        manager = PluginManager(config_file=config_file)

    connectors = manager.connectors(include_disabled=True)
    assert [definition.name for definition in connectors] == ["outlook", "drive"]
    assert connectors[0].module == "pkg.one"
    assert connectors[0].config == {"a": 1}
    assert any("Duplicate connector name 'outlook'" in record.message for record in caplog.records)
