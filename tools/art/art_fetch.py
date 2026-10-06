"""A museum fetch held to the host's remote-fetch policy (art backgrounds plan, step 6).

The library cannot import the host, so this is that policy, as far as an authoring tool run on a
curator's machine needs it: HTTPS on port 443 to an exact allowlist of hosts, no credentials in a
URL, every redirect hop checked against the allowlist (three at most), no host that resolves to
a private, loopback or otherwise non-global address, one overall deadline, bounded bytes, and no
cookies or credentials sent. Unlike the host's, it does not pin the connection to the address it
checked: a museum whose DNS changes between the check and the connect is trusted that far.
"""

from __future__ import annotations

import ipaddress
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

USER_AGENT = "Denframe library curation (+https://denframe.com/library)"
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 30.0

#: The whole fetch, every hop and the body included, ends by then.
DEADLINE_SECONDS = 120.0
_CHUNK = 256 * 1024

#: Metadata is small; a museum's largest allowed image is not.
METADATA_BYTES = 2 * 1024 * 1024
IMAGE_BYTES = 64 * 1024 * 1024


class FetchError(Exception):
    """A fetch the policy refused, or that did not answer as it should."""


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    content_type: str
    body: bytes


Fetcher = Callable[..., Response]


def _global_host(host: str) -> None:
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError(f"{host} does not resolve") from exc
    for answer in answers:
        address = ipaddress.ip_address(answer[4][0])
        if not address.is_global:
            raise FetchError(f"{host} resolves to a non-global address")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _read(answer: Any, max_bytes: int, deadline: float, url: str) -> bytes:
    """The body in chunks, so neither its size nor the deadline can be outrun by a slow server."""
    chunks: list[bytes] = []
    size = 0
    while size <= max_bytes:
        if time.monotonic() > deadline:
            raise FetchError(f"{url} took longer than {DEADLINE_SECONDS:.0f} seconds")
        chunk = answer.read(min(_CHUNK, max_bytes + 1 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks)


def fetch_https(
    url: str,
    *,
    allowed_hosts: Collection[str],
    max_bytes: int = METADATA_BYTES,
    headers: dict[str, str] | None = None,
) -> Response:
    """GET `url` under the policy above; a 404 or 410 is returned for the provider to read."""
    allowed = {host.casefold() for host in allowed_hosts}
    deadline = time.monotonic() + DEADLINE_SECONDS
    for _hop in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        host = (parts.hostname or "").casefold()
        if parts.scheme != "https" or parts.port not in (None, 443):
            raise FetchError(f"{url} is not HTTPS on port 443")
        if parts.username is not None or parts.password is not None:
            raise FetchError(f"{host} names credentials in its URL")
        if host not in allowed:
            raise FetchError(f"{host} is not an allowed host")
        _global_host(host)
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, **(headers or {})}, method="GET"
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError(f"{url} took longer than {DEADLINE_SECONDS:.0f} seconds")
        try:
            with _OPENER.open(request, timeout=min(TIMEOUT_SECONDS, remaining)) as answer:
                body = _read(answer, max_bytes, deadline, url)
                status = answer.status
                content_type = answer.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urljoin(url, exc.headers["Location"])
                continue
            return Response(url, exc.code, exc.headers.get("Content-Type", ""), b"")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchError(f"{host} did not answer: {exc}") from exc
        if len(body) > max_bytes:
            raise FetchError(f"{url} is larger than {max_bytes} bytes")
        return Response(url, status, content_type, body)
    raise FetchError(f"{url} redirects more than {MAX_REDIRECTS} times")
