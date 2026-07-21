"""Swappable generate-image seam, with Black Forest Labs FLUX.2 pro behind it.

The seam is one method::

    backend.generate(reference_image: bytes, scene_prompt: str) -> bytes

Given a reference image (Sophia's curated portrait/pose) and a free-text scene,
it returns the bytes of a new in-character image. BFL is the only implementation
today (per ADR-0002 — the box holds a BFL ``bfl_…`` key in ``FLUX_API``, not a
FAL key), but nothing BFL-specific leaks past ``ImageBackend`` / ``ImageBackendError``,
so moving to FAL later is a one-file change: write another class with the same
method and swap it in.

BFL FLUX.2 pro is a submit-then-poll async API. ``generate`` POSTs the request
(reference sent INLINE as base64 in the body — nothing is uploaded to a public
URL or third-party host), polls the returned polling URL until the result is
``Ready``, then downloads the sample bytes. ``safety_tolerance`` rides on every
submit as the second content ceiling (the first is the tool-side sanitizer from
0013).

Two security-relevant rules hold here:

* The ``FLUX_API`` key is read from the environment per call and only ever placed
  in the ``x-key`` request header. It is never logged, echoed, or returned.
* Every backend problem — a non-200 from submit/poll/download, a BFL moderation
  block, an exhausted poll, or a transport blowing up — is normalized to
  ``ImageBackendError``. No raw ``urllib``/socket exception crosses the seam, so
  the caller (the 0016 tool) can turn any failure into an in-character soft-fail
  with a single ``except ImageBackendError``.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol

# BFL FLUX.2 pro, direct API. The reference goes in the body as base64 under this
# key; the result comes back as a signed sample URL we download from.
BFL_SUBMIT_URL = "https://api.bfl.ai/v1/flux-2-pro"

# 0..6, lower is stricter. BFL's image-input endpoints cap this at 2, and this is
# the *second* no-nudity ceiling behind the tool-side sanitizer, so we pin the
# strictest value the endpoint accepts rather than leaving it to chance.
DEFAULT_SAFETY_TOLERANCE = 2

# BFL polling statuses. "Ready" carries the result; the moderation and error
# statuses are terminal; anything else (Pending/Queued/Processing) means keep
# polling.
_READY = "Ready"
_MODERATION_STATUSES = frozenset({"Request Moderated", "Content Moderated"})
_ERROR_STATUSES = frozenset({"Error", "Task not found", "Task Not Found"})


class ImageBackendError(Exception):
    """A clean, typed failure at the generate-image seam.

    ``reason`` is a stable machine-readable tag the caller can branch on without
    parsing message text:

    * ``config``            — no ``FLUX_API`` key in the environment
    * ``transport``         — the HTTP transport raised (socket/DNS/TLS/etc.)
    * ``submit_failed``     — non-200 on the submit POST
    * ``poll_failed``       — non-200 on a poll GET
    * ``download_failed``   — non-200 fetching the result sample
    * ``moderation``        — BFL refused the request or the output on content grounds
    * ``generation_failed`` — BFL reported a terminal error status
    * ``timeout``           — the result was not ready within the poll budget
    * ``malformed``         — a 200 response was missing fields we require
    """

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass
class HttpResponse:
    """A minimal HTTP response: just what the backend reads off the wire."""

    status: int
    body: bytes

    def json(self) -> dict:
        return json.loads(self.body)


class HttpTransport(Protocol):
    """The injectable HTTP seam. Tests supply a fake; prod uses urllib.

    One method covers submit (POST), poll (GET), and download (GET) so the whole
    flow is drivable with a single recorded/queued double and never touches the
    network in tests.
    """

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        body: bytes | None = None,
    ) -> HttpResponse: ...


class UrllibTransport:
    """Default transport over the standard library — no third-party HTTP dep.

    An HTTP error status (4xx/5xx) is returned as an ``HttpResponse`` so the
    backend can map it to a typed failure uniformly; lower-level failures
    (URLError, timeouts, socket errors) propagate and are wrapped by the backend.
    """

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        body: bytes | None = None,
    ) -> HttpResponse:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return HttpResponse(status=resp.status, body=resp.read())
        except urllib.error.HTTPError as exc:
            # A response with a non-2xx status — carry it through as data.
            return HttpResponse(status=exc.code, body=exc.read())


class ImageBackend(Protocol):
    """The one-method seam every image backend implements."""

    def generate(self, reference_image: bytes, scene_prompt: str) -> bytes: ...


class BflFluxBackend:
    """Black Forest Labs FLUX.2 pro, direct API, behind :class:`ImageBackend`."""

    def __init__(
        self,
        transport: HttpTransport | None = None,
        *,
        submit_url: str = BFL_SUBMIT_URL,
        api_key_env: str = "FLUX_API",
        safety_tolerance: int = DEFAULT_SAFETY_TOLERANCE,
        max_poll_attempts: int = 60,
        poll_interval: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._transport = transport or UrllibTransport()
        self._submit_url = submit_url
        self._api_key_env = api_key_env
        self._safety_tolerance = safety_tolerance
        self._max_poll_attempts = max_poll_attempts
        self._poll_interval = poll_interval
        self._sleep = sleep

    def generate(self, reference_image: bytes, scene_prompt: str) -> bytes:
        """Edit the reference by the scene prompt and return the image bytes."""
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise ImageBackendError(
                "config",
                f"{self._api_key_env} is not set; cannot reach the image backend",
            )

        polling_url = self._submit(reference_image, scene_prompt, api_key)
        sample_url = self._poll_until_ready(polling_url, api_key)
        return self._download(sample_url)

    # -- BFL steps ---------------------------------------------------------

    def _submit(self, reference_image: bytes, scene_prompt: str, api_key: str) -> str:
        payload = {
            "prompt": scene_prompt,
            # Reference travels inline as base64 — never a URL to a public host.
            "input_image": base64.b64encode(reference_image).decode("ascii"),
            "safety_tolerance": self._safety_tolerance,
            "output_format": "png",
        }
        resp = self._call(
            "POST",
            self._submit_url,
            api_key,
            body=json.dumps(payload).encode("utf-8"),
        )
        if resp.status != 200:
            raise ImageBackendError(
                "submit_failed", f"submit returned HTTP {resp.status}"
            )
        data = self._parse(resp, "submit")
        polling_url = data.get("polling_url")
        if not polling_url:
            raise ImageBackendError(
                "malformed", "submit response had no polling_url"
            )
        return polling_url

    def _poll_until_ready(self, polling_url: str, api_key: str) -> str:
        for attempt in range(self._max_poll_attempts):
            resp = self._call("GET", polling_url, api_key)
            if resp.status != 200:
                raise ImageBackendError(
                    "poll_failed", f"poll returned HTTP {resp.status}"
                )
            data = self._parse(resp, "poll")
            status = data.get("status")

            if status == _READY:
                sample_url = (data.get("result") or {}).get("sample")
                if not sample_url:
                    raise ImageBackendError(
                        "malformed", "ready poll had no result.sample URL"
                    )
                return sample_url
            if status in _MODERATION_STATUSES:
                raise ImageBackendError(
                    "moderation", f"BFL blocked the generation: {status}"
                )
            if status in _ERROR_STATUSES:
                raise ImageBackendError(
                    "generation_failed", f"BFL reported status {status}"
                )

            # Pending / Queued / Processing — wait, then poll again.
            if attempt < self._max_poll_attempts - 1:
                self._sleep(self._poll_interval)

        raise ImageBackendError(
            "timeout",
            f"result not ready after {self._max_poll_attempts} polls",
        )

    def _download(self, sample_url: str) -> bytes:
        resp = self._call("GET", sample_url, api_key=None)
        if resp.status != 200:
            raise ImageBackendError(
                "download_failed", f"download returned HTTP {resp.status}"
            )
        return resp.body

    # -- helpers -----------------------------------------------------------

    def _call(
        self,
        method: str,
        url: str,
        api_key: str | None,
        *,
        body: bytes | None = None,
    ) -> HttpResponse:
        """Make one transport call, normalizing any raw exception to typed.

        ``api_key`` is attached as the ``x-key`` header for BFL API calls and
        omitted when downloading the already-authorized sample URL.
        """
        headers = {"accept": "application/json"}
        if api_key is not None:
            headers["x-key"] = api_key
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            return self._transport.request(method, url, headers=headers, body=body)
        except ImageBackendError:
            raise
        except Exception as exc:  # noqa: BLE001 — the seam must not leak raw errors
            raise ImageBackendError(
                "transport", f"HTTP transport failed: {type(exc).__name__}"
            ) from exc

    @staticmethod
    def _parse(resp: HttpResponse, stage: str) -> dict:
        try:
            return resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ImageBackendError(
                "malformed", f"{stage} response was not valid JSON"
            ) from exc
