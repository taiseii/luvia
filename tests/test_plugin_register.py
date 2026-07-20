"""The Hermes plugin adapter: register(ctx) wires luvia's tool functions into the
host's tool registry. A fake ctx records register_tool calls so we can assert the
contract without the hermes-agent runtime present."""

import yaml


class FakeCtx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, toolset, schema, handler, description="", **kwargs):
        self.tools[name] = {
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            "description": description,
        }


def _manifest_tools():
    with open("plugin/plugin.yaml") as f:
        return yaml.safe_load(f)["provides_tools"]


def test_register_wires_every_manifest_tool():
    import plugin

    ctx = FakeCtx()
    plugin.register(ctx)

    assert set(ctx.tools) == set(_manifest_tools())
    for entry in ctx.tools.values():
        assert entry["toolset"] == "luvia"
        assert callable(entry["handler"])


def test_handler_dispatches_args_dict_to_tool(tmp_path, monkeypatch):
    """Registry calls handler(args, **kwargs); the adapter must splat args into
    the tool and ignore host-supplied context kwargs."""
    monkeypatch.setenv("LUVIA_DB", str(tmp_path / "luvia.db"))
    import plugin

    ctx = FakeCtx()
    plugin.register(ctx)

    handler = ctx.tools["luvia_score_response"]["handler"]
    # Extra kwargs (task_id/session_id the host passes) must be absorbed.
    result = handler({"answer": "dankjewel", "expected": "dankjewel"}, task_id="t1")
    assert result["verdict"] == "exact"


def test_every_schema_is_well_formed():
    import plugin

    ctx = FakeCtx()
    plugin.register(ctx)

    for name, entry in ctx.tools.items():
        params = entry["schema"]["parameters"]
        assert params["type"] == "object"
        assert entry["schema"]["description"]
        # required must be a subset of declared properties
        assert set(params.get("required", [])) <= set(params["properties"]), name


def test_setup_and_score_declare_their_required_params():
    import plugin

    ctx = FakeCtx()
    plugin.register(ctx)

    setup_req = ctx.tools["luvia_setup"]["schema"]["parameters"]["required"]
    assert set(setup_req) == {"name", "telegram_user_id"}
    score_req = ctx.tools["luvia_score_response"]["schema"]["parameters"]["required"]
    assert set(score_req) == {"answer", "expected"}
