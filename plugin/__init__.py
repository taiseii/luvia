"""Hermes plugin adapter.

Hermes loads a plugin by importing this package and calling ``register(ctx)``.
The tool logic lives in ``tools.py`` as plain functions; here we describe each
one to the host with a JSON schema and hand it a thin handler. The registry
invokes a handler as ``handler(args, **kwargs)`` where ``args`` is the tool-call
argument dict, so every handler just splats ``args`` into its function and
absorbs any host-supplied context in ``**_``.

Internal ``now`` seams are deliberately omitted from the schemas — the agent
never sets the clock; only tests do.
"""

from __future__ import annotations

import json

from . import tools

TOOLSET = "luvia"


def _handler(fn):
    def handler(args, **_):
        # Hermes' tool registry accepts only a str result (or a multimodal
        # envelope); a raw dict is rejected as `tool_result_contract` and the
        # call silently fails. luvia tools return dicts, so serialize to a JSON
        # string the agent reads back. default=str covers Path/datetime fields
        # (e.g. luvia_selfie's saved-file path).
        return json.dumps(fn(**args), ensure_ascii=False, default=str)

    return handler


# One schema per tool. Shape is the OpenAI function body (the registry adds the
# outer {"type": "function"} wrapper and injects "name").
_TOOLS = (
    (
        tools.luvia_setup,
        "Create the learner and capture onboarding context (interests, contexts, level).",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "telegram_user_id": {"type": "string"},
                "target_lang": {"type": "string", "default": "nl"},
                "timezone": {"type": "string", "default": "Europe/Amsterdam"},
                "reference_lang": {"type": "string", "default": "en"},
                "interests": {"type": "array", "items": {"type": "string"}},
                "contexts": {"type": "array", "items": {"type": "string"}},
                "level": {"type": "string"},
            },
            "required": ["name", "telegram_user_id"],
        },
    ),
    (
        tools.luvia_set_method,
        "Switch the learner's active method profile (persists in the learner record).",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "method_profile_id": {"type": "string"},
            },
            "required": ["user_id", "method_profile_id"],
        },
    ),
    (
        tools.luvia_plan_today,
        "The daily plan from SQLite state alone: pacing band, due load, new intake, mode balance.",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "lang": {"type": "string"},
            },
            "required": ["user_id", "lang"],
        },
    ),
    (
        tools.luvia_pick_items,
        "Return a mode-aware batch for the current burst: due reviews, or a due+new micro-batch for ambient.",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "mode": {"type": "string", "enum": ["ambient", "review"]},
                "lang": {"type": "string"},
                "batch_size": {"type": "integer"},
            },
            "required": ["user_id", "mode", "lang"],
        },
    ),
    (
        tools.luvia_record_result,
        "Log a session event and reschedule the item in one transaction. Pass session_id, or lang+mode to attach to the current burst. grade is one of again/good/easy/already_knew, or null for an ungraded signal.",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "item_id": {"type": "integer"},
                "grade": {"type": ["string", "null"], "enum": ["again", "good", "easy", "already_knew", None]},
                "mechanism": {"type": "string"},
                "session_id": {"type": "integer"},
                "lang": {"type": "string"},
                "mode": {"type": "string"},
                "latency_ms": {"type": "integer"},
                "comprehension_break": {"type": "boolean"},
                "prompt": {"type": "string"},
                "learner_response": {"type": "string"},
                "score": {"type": "number"},
                "feedback": {"type": "string"},
            },
            "required": ["user_id", "item_id", "grade", "mechanism"],
        },
    ),
    (
        tools.luvia_score_response,
        "Deterministically score a typed answer against the accepted answer(s).",
        {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "expected": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ]
                },
            },
            "required": ["answer", "expected"],
        },
    ),
    (
        tools.luvia_stats,
        "A read-only 'is this working' snapshot: recall rate, sweep progress, band position, due counts.",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "lang": {"type": "string"},
            },
            "required": ["user_id", "lang"],
        },
    ),
    (
        tools.luvia_selfie,
        "Generate an in-character selfie by editing a fixed reference of Sophia with a scene. Returns {ok, path, ...} on success (deliver the path via send_message MEDIA:<path> <caption>); on any block/cap/failure returns a soft-fail {ok: false, reason, ...} to absorb in character — it never errors. reference_role defaults to canonical_face; trigger_source is 'proactive' (rare, routine-tied) or 'request'.",
        {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "scene": {"type": "string"},
                "reference_role": {"type": "string", "default": "canonical_face"},
                "trigger_source": {
                    "type": "string",
                    "enum": ["proactive", "request"],
                    "default": "request",
                },
            },
            "required": ["user_id", "scene"],
        },
    ),
)


def register(ctx):
    """Register every luvia tool with the host tool registry."""
    for fn, description, parameters in _TOOLS:
        ctx.register_tool(
            name=fn.__name__,
            toolset=TOOLSET,
            schema={"description": description, "parameters": parameters},
            handler=_handler(fn),
            description=description,
        )
