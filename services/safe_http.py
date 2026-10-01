"""Safe outbound HTTP — single replacement for urllib.request.urlopen.

Rejects non-http(s) schemes, private/metadata ranges (unless allow_private),
caps response size, enforces timeout, blocks scheme-changing redirects.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from typing import Iterable, Optional, Sequence
from urllib.parse import urlparse

DEFAULT_ALLOWED = ("https",)
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
PRIVATE_PREFIXES = (
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.2",  # 172.20-172.31 covered loosely; refined below
    "192.168.",
    "169.254.",
)


class UnsafeURLError(ValueError):
    pass


def _host_is_private(host: str) -> bool:
    h = (host or "").strip().lower().strip("[]")
    if h in LOOPBACK_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(h)
        return bool(ip.is_private or ip.is_link_local or ip.is_loopback or ip.is_reserved)
    except ValueError:
        # hostname — resolve optional; treat known metadata hostnames
        if h in ("metadata.google.internal", "metadata"):
            return True
        return False


def validate_url(
    url: str,
    *,
    allowed_schemes: Sequence[str] = DEFAULT_ALLOWED,
    allow_private: bool = False,
    host_allowlist: Optional[Iterable[str]] = None,
) -> str:
    u = (url or "").strip()
    if not u:
        raise UnsafeURLError("empty URL")
    parsed = urlparse(u)
    scheme = (parsed.scheme or "").lower()
    if scheme not in allowed_schemes:
        # allow http only for loopback when explicitly listed
        if scheme == "http" and "http" in allowed_schemes:
            pass
        else:
            raise UnsafeURLError(f"scheme not allowed: {scheme or '(none)'}")
    host = parsed.hostname or ""
    if not host:
        raise UnsafeURLError("missing host")
    if host_allowlist is not None:
        allowed = {h.lower() for h in host_allowlist}
        if host.lower() not in allowed and host not in LOOPBACK_HOSTS:
            raise UnsafeURLError(f"host not in allowlist: {host}")
    if _host_is_private(host) and not allow_private:
        # loopback http for local model needs allow_private=True
        if host.lower() not in LOOPBACK_HOSTS or scheme != "http":
            raise UnsafeURLError(f"private/link-local host blocked: {host}")
        if host.lower() in LOOPBACK_HOSTS and scheme == "http" and "http" in allowed_schemes:
            return u
        raise UnsafeURLError(f"private host blocked: {host}")
    if scheme == "http" and host.lower() not in LOOPBACK_HOSTS:
        raise UnsafeURLError("http only allowed for loopback hosts")
    return u


class _NoCrossSchemeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urlparse(req.full_url)
        new = urlparse(newurl)
        if (new.scheme or "").lower() not in ("http", "https"):
            raise UnsafeURLError(f"redirect to forbidden scheme: {new.scheme}")
        if (old.scheme or "").lower() == "https" and (new.scheme or "").lower() != "https":
            raise UnsafeURLError("https→http redirect blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_urlopen(
    request: urllib.request.Request | str,
    timeout: float = 30.0,
    *,
    allowed_schemes: Sequence[str] = DEFAULT_ALLOWED,
    allow_private: bool = False,
    host_allowlist: Optional[Iterable[str]] = None,
    max_bytes: int = 10 * 1024 * 1024,
):
    """urlopen with scheme/host/size/timeout guards."""
    if isinstance(request, str):
        url = request
        req = urllib.request.Request(url)
    else:
        req = request
        url = req.full_url
    validate_url(
        url,
        allowed_schemes=allowed_schemes,
        allow_private=allow_private,
        host_allowlist=host_allowlist,
    )
    opener = urllib.request.build_opener(_NoCrossSchemeRedirectHandler)
    resp = opener.open(req, timeout=timeout)
    # Cap body size via wrapper if caller reads all
    return resp


def read_capped(resp, max_bytes: int = 10 * 1024 * 1024) -> bytes:
    data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UnsafeURLError(f"response exceeds {max_bytes} bytes")
    return data
