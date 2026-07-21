"""Tests for the swappable generate-image seam and its BFL FLUX.2 pro backend.

The seam is one method: ``generate(reference_image, scene_prompt) -> bytes``.
BFL is one implementation behind it. Every test injects a fake HTTP transport —
there is NO live network here, and no real API key is ever used. The transport
records the requests the backend makes so we can assert their shape (reference
sent inline as base64, ``safety_tolerance`` present, key taken from ``FLUX_API``),
and it queues the responses that drive the submit-then-poll-then-download flow.

A second cluster of tests exercises the security posture: response-supplied URLs
(``polling_url``, ``result.sample``) are untrusted, so an attacker/``file://``/
non-BFL host must be rejected before any request carrying the key is made; the
key must never surface in an error or its cause chain; bodies are size-capped;
and the ``safety_tolerance`` content ceiling is pinned in code.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from plugin.image_backend import (
    MAX_JSON_BYTES,
    STRICT_SAFETY_TOLERANCE,
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

    def request(self, method, url, *, headers, body=None, max_bytes=None):
        self.calls.append(
            SimpleNamespace(
                method=method,
                url=url,
                headers=dict(headers),
                body=body,
                max_bytes=max_bytes,
            )
        )
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _json_response(payload, status=200):
    return HttpResponse(status=status, body=json.dumps(payload).encode("utf-8"))


def _submit_ok():
    return _json_response({"id": "req-123", "polling_url": POLLING_URL})


def _submit_with_polling_url(url):
    return _json_response({"id": "req-123", "polling_url": url})


def _poll(status, **extra):
    return _json_response({"status": status, **extra})


def _poll_ready(sample=SAMPLE_URL):
    return _poll("Ready", result={"sample": sample})


def _download_ok(body=RESULT_BYTES):
    return HttpResponse(status=200, body=body)


def _make_backend(transport, **kwargs):
    # sleep is a no-op so the poll loop never actually blocks in tests.
    kwargs.setdefault("submit_url", SUBMIT_URL)
    kwargs.setdefault("sleep", lambda _seconds: None)
    kwargs.setdefault("max_poll_attempts", 5)
    return BflFluxBackend(transport=transport, **kwargs)


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


def test_submit_sends_json_content_type():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "on the balcony")

    assert transport.calls[0].headers["Content-Type"] == "application/json"


def test_safety_tolerance_pinned_to_strict_value():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "walking the dog")

    payload = json.loads(transport.calls[0].body)
    # The exact value matters, not just presence: this is the server-side ceiling.
    assert payload["safety_tolerance"] == 2
    assert payload["safety_tolerance"] == STRICT_SAFETY_TOLERANCE


def test_lax_safety_tolerance_is_rejected():
    transport = FakeTransport([])

    with pytest.raises(ImageBackendError) as excinfo:
        _make_backend(transport, safety_tolerance=6)

    assert excinfo.value.reason == "config"
    # Refused at construction — no request was ever attempted.
    assert transport.calls == []


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


def test_download_carries_no_api_key():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "signed delivery link")

    # The sample URL is a signed delivery link on a non-API host; the key must
    # not ride along on the download.
    assert "x-key" not in transport.calls[2].headers


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


def test_bfl_failed_status_is_immediate_generation_failure():
    # "Failed" is terminal — it must fail fast, not poll to timeout.
    transport = FakeTransport([_submit_ok(), _poll("Failed")])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "failed job")

    assert excinfo.value.reason == "generation_failed"
    # 1 submit + 1 poll only — no waiting out the whole poll budget.
    assert len(transport.calls) == 2


# --- security: SSRF guard on response-supplied URLs -----------------------


def test_attacker_polling_url_is_rejected_without_leaking_key():
    attacker = "https://attacker.example.com/steal-the-key"
    transport = FakeTransport([_submit_with_polling_url(attacker)])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "poisoned polling url")

    assert excinfo.value.reason == "untrusted_url"
    # Only the submit call happened — the poll to the attacker host, which would
    # have carried the x-key, was never made.
    assert len(transport.calls) == 1
    assert all(attacker not in c.url for c in transport.calls)


def test_lookalike_polling_host_is_rejected():
    lookalike = "https://api.evil-bfl.ai/get_result?id=x"
    transport = FakeTransport([_submit_with_polling_url(lookalike)])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "lookalike host")

    assert excinfo.value.reason == "untrusted_url"
    assert len(transport.calls) == 1


def test_attacker_sample_url_is_rejected_before_download():
    attacker = "https://attacker.example.com/exfil.png"
    transport = FakeTransport([_submit_ok(), _poll_ready(sample=attacker)])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "poisoned sample url")

    assert excinfo.value.reason == "untrusted_url"
    # submit + poll only; the download to the attacker host never happened.
    assert len(transport.calls) == 2
    assert all(attacker not in c.url for c in transport.calls)


def test_file_scheme_sample_url_is_rejected():
    transport = FakeTransport(
        [_submit_ok(), _poll_ready(sample="file:///etc/passwd")]
    )
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "file scheme")

    assert excinfo.value.reason == "untrusted_url"
    assert len(transport.calls) == 2


def test_non_bfl_delivery_host_is_rejected():
    transport = FakeTransport(
        [_submit_ok(), _poll_ready(sample="https://cdn.example.net/img.png")]
    )
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "wrong delivery host")

    assert excinfo.value.reason == "untrusted_url"


# --- security: no key in errors / cause chain -----------------------------


def _chain_texts(err):
    texts = []
    seen = set()
    cur = err
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        texts.append(str(cur))
        texts.append(repr(cur))
        texts.append(repr(cur.args))
        cur = cur.__cause__ or cur.__context__
    return " ".join(texts)


def test_key_never_appears_in_error_or_cause_chain():
    # The underlying exception text embeds the key to prove it can't propagate.
    leaky = RuntimeError(f"connection failed with header x-key={FAKE_KEY}")
    transport = FakeTransport([leaky])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "leaky exception")

    err = excinfo.value
    assert err.reason == "transport"
    # The cause chain is severed (`from None`), so the leaky original can't be
    # walked to recover the key.
    assert err.__cause__ is None
    assert FAKE_KEY not in str(err)
    assert FAKE_KEY not in repr(err)
    assert FAKE_KEY not in _chain_texts(err)


# --- security: bounded reads ----------------------------------------------


def test_oversize_response_is_typed_failure():
    oversize = HttpResponse(
        status=200,
        body=b"{}",
        headers={"Content-Length": str(MAX_JSON_BYTES + 1)},
    )
    transport = FakeTransport([oversize])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "huge response")

    assert excinfo.value.reason == "oversize"


def test_oversize_body_without_content_length_is_rejected():
    # No Content-Length header, but the body itself blows the cap.
    oversize = HttpResponse(status=200, body=b"x" * (MAX_JSON_BYTES + 1))
    transport = FakeTransport([oversize])
    backend = _make_backend(transport)

    with pytest.raises(ImageBackendError) as excinfo:
        backend.generate(REFERENCE_BYTES, "oversize body")

    assert excinfo.value.reason == "oversize"


def test_reads_are_bounded_with_max_bytes():
    transport = FakeTransport([_submit_ok(), _poll_ready(), _download_ok()])
    backend = _make_backend(transport)

    backend.generate(REFERENCE_BYTES, "bounded reads")

    # Every call passed a positive byte cap down to the transport.
    assert all(c.max_bytes and c.max_bytes > 0 for c in transport.calls)
