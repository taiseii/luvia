import re
from pathlib import Path

import yaml

MANIFEST = Path(__file__).parent.parent / "plugin" / "plugin.yaml"


def test_manifest_declares_tool_surface():
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert manifest["name"] == "luvia"
    assert manifest["version"]
    assert manifest["kind"]
    assert "luvia_setup" in manifest["tools"]
    for tool in manifest["tools"]:
        assert re.fullmatch(r"luvia_[a-z0-9_]+", tool)


def test_manifest_tools_exist_in_package():
    from plugin import tools as tools_module

    manifest = yaml.safe_load(MANIFEST.read_text())
    for tool in manifest["tools"]:
        assert callable(getattr(tools_module, tool))
