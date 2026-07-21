"""Tests for the swappable generate-image seam and its BFL FLUX.2 pro backend.

The seam is one method: ``generate(reference_image, scene_prompt) -> bytes``.
BFL is one implementation behind it. Every test injects a fake HTTP transport —
there is NO live network here, and no real API key is ever used. The transport
records the requests the backend makes so we can assert their shape (reference
sent inline as base64, ``safety_tolerance`` present, key taken from ``FLUX_API``),
and it queues the responses that drive the submit-then-poll-then-download flow.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from plugin.image_backend import (
    BflFluxBackend,
    HttpResponse,
    ImageBackendError,
)

FAKE_KEY = "bfl_test_deadbeef_not_a_real_key"
REFERENCE_BYTES = b"\x89PNG\r\n\x1a\n reference portrait pixels"
RESULT_BYTES = b"\x89PNG\r\n\x1a\n generated selfie pixels"
SUBMIT_URL = "https://api.bfl.ai/v1/flux-2-pro"
POLLING_URL = "https://api.bfl.ai/v1/get_result?id=req-123"
SAMPLE_URL = "https://delivery.bfl.ai/results/req-123.png"


class FakeTransport:
    """Deterministic in-memory HTTP double.

    ``responses`` is a queue consumed in order — each item is either an
    ``HttpResponse`` to return or an ``Exception`` to raise (to model a socket
    blowing up mid-call). Every call is recorded in ``calls`` for shape asserts.
    """

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers, body=None):
        self.calls.append(
            SimpleNamespace(method=method, url=url, headers=dict(headers), body=body)
        )
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _json_response(payload, status=200):
    return HttpResponse(status=status, body=json.dumps(payload).encode("utf-8"))


def _submit_ok():
    return _json_response({"id": "req-123", "polling_url": POLLING_URL})


def _poll(status, **extra):
    return _json_response({"status": status, **extra})


def _poll_ready():
    return _poll("Ready", result={"sample": SAMPLE_URL})


def _download_ok(body=RESULT_BYTES):
    return HttpResponse(status=200, body=body)


def _make_backend(transport):
    # sleep is a no-op so the poll loop never actually blocks in tests.
    return BflFluxBackend(
        transport=transport,
        submit_url=SUBMIT_URL,
        sleep=lambda _seconds: None,
        max_poll_attempts=5,
    )


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FLUX_API", FAKE_KEY)


# --- happy path: bytes out ------------------------------------------------


def test_generate_returns_downloaded_image_bytes():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    out = backend.generate(REFERENCE_BYTES, "at the gym, mirror selfie")

    assert out == RESULT_BYTES


def test_generate_makes_submit_poll_download_calls():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "café latte")

    methods = [(c.method, c.url) for c in transport.calls]
    assert methods[0] == ("POST", SUBMIT_URL)
    assert methods[1] == ("GET", POLLING_URL)
    assert methods[2] == ("GET", SAMPLE_URL)


# --- request shape --------------------------------------------------------


def test_reference_is_sent_inline_as_base64():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "bedroom, soft light")

    submit = transport.calls[0]
    payload = json.loads(submit.body)
    # The reference travels in the body as base64, never as a URL to a host.
    encoded = payload["input_image"]
    assert base64.b64decode(encoded) == REFERENCE_BYTES
    assert "http" not in encoded  # it is data, not a link


def test_safety_tolerance_present_on_submit():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "walking the dog")

    payload = json.loads(transport.calls[0].body)
    assert "safety_tolerance" in payload
    assert isinstance(payload["safety_tolerance"], int)


def test_scene_prompt_is_forwarded():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "sunset run along the canal")

    payload = json.loads(transport.calls[0].body)
    assert payload["prompt"] == "sunset run along the canal"


def test_api_key_taken_from_flux_api_env():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "morning coffee")

    # BFL authenticates with the x-key header; it must be the FLUX_API value.
    assert transport.calls[0].headers["x-key"] == FAKE_KEY
    # And the poll call is authenticated too.
    assert transport.calls[1].headers["x-key"] == FAKE_KEY


def test_missing_flux_api_key_is_typed_failure(monkeypatch):
    monkeypatch.delenv("FLUX_API", raising=False)
    transport = FakeTransport([])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "anything")

    assert excinfo.value.reason == "config"
    # Nothing was even attempted over the wire.
    assert transport.calls == []


# --- submit-then-poll flow ------------------------------------------------


def test_pending_then_ready_polls_until_done():
    transport = FakeTransport(
        [
            _submit_ok(),
            _poll("Pending"),
            _poll("Pending"),
            _poll_ready(),
            _download_ok(),
        ]
    )
    backend = _make_backend(transport)

    out = backend.generate(REFERENCE_BYTES, "still generating…")

    assert out == RESULT_BYTES
    # 1 submit + 3 polls + 1 download.
    assert len(transport.calls) == 5


# --- typed failures: no raw HTTP exception crosses the seam ---------------


def test_non_200_submit_is_typed_failure():
    transport = FakeTransport([HttpResponse(status=500, body=b"upstream boom")])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "boom")

    assert excinfo.value.reason == "submit_failed"


def test_non_200_poll_is_typed_failure():
    transport = FakeTransport([_submit_ok(), HttpResponse(status=502, body=b"bad")])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "bad gateway")

    assert excinfo.value.reason == "poll_failed"


def test_non_200_download_is_typed_failure():
    transport = FakeTransport(
        [_submit_ok(), _poll_ready(), HttpResponse(status=404, body=b"gone")]
    )
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "expired sample")

    assert excinfo.value.reason == "download_failed"


def test_moderation_block_is_typed_failure():
    transport = FakeTransport([_submit_ok(), _poll("Content Moderated")])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "blocked scene")

    assert excinfo.value.reason == "moderation"


def test_request_moderated_is_typed_failure():
    transport = FakeTransport([_submit_ok(), _poll("Request Moderated")])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "blocked input")

    assert excinfo.value.reason == "moderation"


def test_poll_timeout_is_typed_failure():
    # Always Pending: the loop must give up after max_poll_attempts, not hang.
    responses = [_submit_ok()] + [_poll("Pending")] * 5
    transport = FakeTransport(responses)
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "never ready")

    assert excinfo.value.reason == "timeout"


def test_transport_exception_is_wrapped_not_leaked():
    transport = FakeTransport([RuntimeError("socket exploded")])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "network down")

    # The raw exception is normalized, not propagated.
    assert not isinstance(excinfo.value, RuntimeError)
    assert excinfo.value.reason == "transport"


def test_bfl_error_status_is_typed_failure():
    transport = FakeTransport([_submit_ok(), _poll("Error")])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "server-side error")

    assert excinfo.value.reason == "generation_failed"
