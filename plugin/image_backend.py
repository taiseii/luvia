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

Security posture — this backend makes authenticated outbound calls to URLs that
come back *in the API response*, so those URLs are treated as untrusted:

* **SSRF / key-leak guard.** Both the ``polling_url`` (polled WITH the ``FLUX_API``
  key in the ``x-key`` header) and the ``result.sample`` download URL are validated
  before any request is made to them: https only, and the host must sit in the
  ``bfl.ai`` domain on the API (``api*.bfl.ai``) or delivery (``delivery*.bfl.ai``)
  allowlist. A poisoned response pointing at ``attacker.example`` or ``file://`` is
  rejected with ``ImageBackendError(reason="untrusted_url")`` and no request — key
  or not — is ever sent to it. The urllib transport also refuses to follow 3xx
  redirects, so a redirect can't bounce an already-validated authenticated request
  to another host.
* **No key in secrets / tracebacks.** The ``FLUX_API`` key is read from the
  environment per call and only ever placed in the ``x-key`` header of a
  host-validated BFL request (never the signed delivery download). It is never
  logged, echoed, or returned, and transport exceptions are re-raised sanitized
  with ``from None`` so the original error's cause chain (which could reference
  request headers) is dropped.
* **Bounded reads.** JSON and image responses are size-capped so a hostile or
  runaway upstream can't exhaust memory.

Every backend problem — a non-200 from submit/poll/download, a BFL moderation
block, an untrusted URL, an oversize body, an exhausted poll, or a transport
blowing up — is normalized to ``ImageBackendError``. No raw ``urllib``/socket
exception crosses the seam, so the caller (the 0016 tool) can turn any failure
into an in-character soft-fail with a single ``except ImageBackendError``.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol

# BFL FLUX.2 pro, direct API. The reference goes in the body as base64 under this
# key; the result comes back as a signed sample URL we download from.
BFL_SUBMIT_URL = "https://api.bfl.ai/v1/flux-2-pro"

# safety_tolerance is 0..6, lower is stricter, and BFL's image-input endpoints cap
# it at 2. It is the *second* no-nudity ceiling behind the tool-side sanitizer, so
# the strict max is pinned in code: 2 is the loosest value this backend will ever
# send, and anything above it is refused rather than trusted.
STRICT_SAFETY_TOLERANCE = 2

# Bounded reads: JSON control responses are tiny; only the final image is large.
MAX_JSON_BYTES = 1 * 1024 * 1024  # 1 MiB — submit/poll/error bodies
MAX_IMAGE_BYTES = 32 * 1024 * 1024  # 32 MiB — the downloaded sample

# BFL polling statuses. "Ready" carries the result; the moderation and error
# statuses are terminal; anything else (Pending/Queued/Processing) means keep
# polling. Documented BFL API hosts live under api*.bfl.ai; signed result
# deliveries under delivery*.bfl.ai.
_READY = "Ready"
_MODERATION_STATUSES = frozenset({"Request Moderated", "Content Moderated"})
_ERROR_STATUSES = frozenset(
    {"Error", "Failed", "Task not found", "Task Not Found"}
)


class ImageBackendError(Exception):
    """A clean, typed failure at the generate-image seam.

    ``reason`` is a stable machine-readable tag the caller can branch on without
    parsing message text:

    * ``config``            — no ``FLUX_API`` key, or an out-of-range safety ceiling
    * ``transport``         — the HTTP transport raised (socket/DNS/TLS/etc.)
    * ``untrusted_url``     — a response-supplied URL failed the https+host allowlist
    * ``oversize``          — a response body exceeded its size cap
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


# --- URL allowlisting (SSRF guard for response-supplied URLs) -------------


def _registrable_is_bfl(host: str) -> bool:
    """True when ``host`` is anchored to the ``bfl.ai`` registrable domain.

    Only BFL controls ``bfl.ai`` DNS, so any ``*.bfl.ai`` host is BFL-operated.
    Look-alikes like ``evil-bfl.ai`` or ``bfl.ai.attacker.com`` fail this check."""
    labels = host.lower().split(".")
    return labels[-2:] == ["bfl", "ai"]


def _is_bfl_api_host(host: str) -> bool:
    labels = host.lower().split(".")
    return _registrable_is_bfl(host) and labels[0] == "api"


def _is_bfl_delivery_host(host: str) -> bool:
    labels = host.lower().split(".")
    first = labels[0]
    return _registrable_is_bfl(host) and (
        first == "delivery" or first.startswith("delivery-")
    )


def _require_trusted_url(url: str, host_ok: Callable[[str], bool]) -> str:
    parts = urllib.parse.urlparse(url)
    if parts.scheme != "https":
        raise ImageBackendError(
            "untrusted_url", f"refusing non-https URL scheme {parts.scheme!r}"
        )
    host = parts.hostname or ""
    if not host_ok(host):
        raise ImageBackendError(
            "untrusted_url", f"refusing URL to untrusted host {host!r}"
        )
    return url


@dataclass
class HttpResponse:
    """A minimal HTTP response: status, body, and response headers."""

    status: int
    body: bytes
    headers: dict = field(default_factory=dict)

    def json(self) -> dict:
        return json.loads(self.body)


class HttpTransport(Protocol):
    """The injectable HTTP seam. Tests supply a fake; prod uses urllib.

    One method covers submit (POST), poll (GET), and download (GET) so the whole
    flow is drivable with a single recorded/queued double and never touches the
    network in tests. ``max_bytes`` lets the caller bound the read.
    """

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        body: bytes | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse: ...


class _NoFollowRedirects(urllib.request.HTTPRedirectHandler):
    """Never follow 3xx: a redirect must not bounce an authenticated, host-
    validated request onto an attacker-chosen host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    """Default transport over the standard library — no third-party HTTP dep.

    An HTTP error status (4xx/5xx) is returned as an ``HttpResponse`` so the
    backend can map it to a typed failure uniformly; lower-level failures
    (URLError, timeouts, socket errors) propagate and are wrapped by the backend.
    Reads are bounded to ``max_bytes + 1`` so an oversize body is detected without
    being fully pulled into memory. Redirects are disabled.
    """

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout
        self._opener = urllib.request.build_opener(_NoFollowRedirects())

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict,
        body: bytes | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        limit = None if max_bytes is None else max_bytes + 1
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                data = resp.read() if limit is None else resp.read(limit)
                return HttpResponse(
                    status=resp.status,
                    body=data,
                    headers=dict(resp.getheaders()),
                )
        except urllib.error.HTTPError as exc:
            data = exc.read() if limit is None else exc.read(limit)
            return HttpResponse(
                status=exc.code, body=data, headers=dict(exc.headers.items())
            )


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
        safety_tolerance: int = STRICT_SAFETY_TOLERANCE,
        max_poll_attempts: int = 60,
        poll_interval: float = 1.5,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if (
            not isinstance(safety_tolerance, int)
            or isinstance(safety_tolerance, bool)
            or safety_tolerance < 0
            or safety_tolerance > STRICT_SAFETY_TOLERANCE
        ):
            # The content ceiling is pinned in code, not left to the caller: a lax
            # value (e.g. 6) must never reach BFL.
            raise ImageBackendError(
                "config",
                f"safety_tolerance must be an int 0..{STRICT_SAFETY_TOLERANCE}",
            )
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
        # Validate BEFORE polling — the poll carries the key, so the host it goes
        # to must be a trusted BFL API host, not whatever the response supplied.
        _require_trusted_url(polling_url, _is_bfl_api_host)

        sample_url = self._poll_until_ready(polling_url, api_key)
        # Validate BEFORE downloading — reject file://, other schemes, non-BFL hosts.
        _require_trusted_url(sample_url, _is_bfl_delivery_host)
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
            max_bytes=MAX_JSON_BYTES,
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
            resp = self._call("GET", polling_url, api_key, max_bytes=MAX_JSON_BYTES)
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
        # No x-key here: the sample URL is already a signed delivery link, and the
        # delivery host is outside the API allowlist — the key must not travel to it.
        resp = self._call("GET", sample_url, api_key=None, max_bytes=MAX_IMAGE_BYTES)
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
        max_bytes: int,
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

        # The raw transport error can reference the request (and thus the x-key
        # header), so it must never chain onto what we surface. We capture only its
        # type name inside the handler, then raise the sanitized error OUTSIDE the
        # except block — raising there leaves both __cause__ and the implicit
        # __context__ empty, so the original (and any key in it) is unreachable.
        transport_error: str | None = None
        try:
            resp = self._transport.request(
                method, url, headers=headers, body=body, max_bytes=max_bytes
            )
        except ImageBackendError:
            raise
        except Exception as exc:  # noqa: BLE001 — the seam must not leak raw errors
            transport_error = type(exc).__name__
        if transport_error is not None:
            raise ImageBackendError(
                "transport", f"HTTP transport failed: {transport_error}"
            )

        self._enforce_size(resp, max_bytes)
        return resp

    @staticmethod
    def _enforce_size(resp: HttpResponse, max_bytes: int) -> None:
        declared = resp.headers.get("Content-Length") or resp.headers.get(
            "content-length"
        )
        if declared is not None:
            try:
                too_big = int(declared) > max_bytes
            except ValueError:
                too_big = False
            if too_big:
                raise ImageBackendError(
                    "oversize",
                    f"response declared {declared} bytes, over the {max_bytes} cap",
                )
        if len(resp.body) > max_bytes:
            raise ImageBackendError(
                "oversize", f"response body exceeded the {max_bytes} byte cap"
            )

    @staticmethod
    def _parse(resp: HttpResponse, stage: str) -> dict:
        try:
            return resp.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ImageBackendError(
                "malformed", f"{stage} response was not valid JSON"
            ) from exc
