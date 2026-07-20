import re
from pathlib import Path

import yaml

MANIFEST = Path(__file__).parent.parent / "plugin" / "plugin.yaml"


def test_manifest_declares_tool_surface():
    manifest = yaml.safe_load(MANIFEST.read_text())

    assert manifest["name"] == "luvia"
    assert manifest["version"]
    assert manifest["manifest_version"] == 1
    assert manifest["kind"] in {"standalone", "backend", "exclusive", "platform", "model-provider"}
    assert "luvia_setup" in manifest["provides_tools"]
    for tool in manifest["provides_tools"]:
        assert re.fullmatch(r"luvia_[a-z0-9_]+", tool)


def test_manifest_tools_exist_in_package():
    from plugin import tools as tools_module

    manifest = yaml.safe_load(MANIFEST.read_text())
    for tool in manifest["provides_tools"]:
        assert callable(getattr(tools_module, tool))


def test_register_matches_manifest():
    """The adapter must register exactly the tools the manifest advertises."""
    import plugin

    class _Ctx:
        def __init__(self):
            self.names = set()

        def register_tool(self, name, **kwargs):
            self.names.add(name)

    ctx = _Ctx()
    plugin.register(ctx)
    manifest = yaml.safe_load(MANIFEST.read_text())
    assert ctx.names == set(manifest["provides_tools"])
