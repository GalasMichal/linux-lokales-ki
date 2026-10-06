"""URL and action rules for the local browser agent. No browser imports."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

from errors import ToolError

ALLOWED_SCHEMES = {"http", "https"}
EMPTY_DOCUMENT = "about:blank"
REF_PREFIX = {
    "link": "l",
    "button": "b",
    "input": "i",
    "textarea": "t",
    "select": "s",
    "checkbox": "c",
    "radio": "c",
}
EXECUTABLE_SUFFIXES = {
    ".appimage",
    ".exe",
    ".msi",
    ".sh",
    ".run",
    ".bin",
    ".desktop",
    ".deb",
    ".rpm",
    ".jar",
    ".bat",
    ".cmd",
    ".ps1",
    ".dmg",
    ".apk",
}
DANGEROUS_NAME = (
    "kaufen",
    "bestellen",
    "bezahlen",
    "checkout",
    "subscribe",
    "abonnement",
    "konto löschen",
    "account löschen",
    "delete account",
    "passwort ändern",
    "change password",
    "e-mail senden",
    "email senden",
    "send email",
    "send message",
    "posten",
    "tweet",
    "upload",
    "hochladen",
    "buy now",
    "submit order",
    "bestellung",
    "in den warenkorb",
    "add to cart",
    "pay now",
    "zahlung",
)
PRIVATE_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".localdomain")


def allow_hosts() -> set[str]:
    raw = os.environ.get("BROWSER_AGENT_ALLOW_HOSTS", "")
    return {item.strip().lower().rstrip(".") for item in raw.split(",") if item.strip()}


def check_navigation_url(url: str) -> str:
    """Return a normalized URL or raise ToolError. Never allows local files or private hosts."""
    raw = (url or "").strip()
    if not raw or any(ord(ch) < 32 for ch in raw):
        raise ToolError("URL ist leer oder enthält Steuerzeichen.")
    if len(raw) > 2000:
        raise ToolError("URL ist zu lang.")
    lowered = raw.lower()
    if lowered.startswith(("javascript:", "data:", "file:", "ftp:", "chrome:", "about:", "blob:", "view-source:")):
        raise ToolError(f"Dieses URL-Schema ist gesperrt: {raw.split(':', 1)[0]}")
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ToolError("Nur http und https sind erlaubt.")
    if parsed.username or parsed.password:
        raise ToolError("URLs mit Benutzername oder Passwort sind gesperrt.")
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise ToolError("URL ohne Host ist gesperrt.")
    if host in allow_hosts():
        return raw
    _assert_public_host(host)
    return raw


def check_request_url(url: str) -> bool:
    """True when a subresource or redirect may load. about:blank is only the empty start page."""
    raw = (url or "").strip()
    if raw == EMPTY_DOCUMENT:
        return True
    try:
        check_navigation_url(raw)
    except ToolError:
        return False
    return True


def classify_control(tag: str, role: str, input_type: str) -> str | None:
    kind = (role or tag or "").lower()
    itype = (input_type or "").lower()
    if kind in {"checkbox", "radio"} or itype in {"checkbox", "radio"}:
        return "checkbox" if itype != "radio" and kind != "radio" else "radio"
    if kind == "a" or kind == "link":
        return "link"
    if kind in {"button", "submit"} or itype in {"button", "submit", "reset"}:
        return "button"
    if kind == "textarea":
        return "textarea"
    if kind == "select":
        return "select"
    if kind == "input" or tag == "input":
        if itype in {"hidden", "submit", "button", "reset", "image", "file"}:
            return "button" if itype in {"submit", "button", "reset", "image"} else None
        return "input"
    return None


def is_dangerous_action(name: str) -> bool:
    text = " ".join((name or "").lower().split())
    if not text:
        return False
    return any(needle in text for needle in DANGEROUS_NAME)


def is_executable_download(name: str) -> bool:
    suffix = os.path.splitext((name or "").lower())[1]
    return suffix in EXECUTABLE_SUFFIXES


def _assert_public_host(host: str) -> None:
    if host in {"localhost", "localhost.localdomain"} or host.endswith(PRIVATE_HOST_SUFFIXES):
        raise ToolError(f"Lokaler Host ist gesperrt: {host}")
    if host.endswith(".arpa"):
        raise ToolError(f"Lokaler Host ist gesperrt: {host}")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        _assert_public_ip(ip, host)
        return
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(3)
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        finally:
            socket.setdefaulttimeout(old_timeout)
    except socket.gaierror as exc:
        raise ToolError(f"Host ist nicht auflösbar: {host}") from exc
    seen = False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        seen = True
        _assert_public_ip(ip, host)
    if not seen:
        raise ToolError(f"Host ist nicht auflösbar: {host}")


def _assert_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, host: str) -> None:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    ):
        raise ToolError(f"Privates oder lokales Ziel ist gesperrt: {host}")
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        _assert_public_ip(ip.ipv4_mapped, host)
    # Carrier-grade NAT 100.64.0.0/10 is not flagged by is_private on all uses; block it.
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
        raise ToolError(f"Privates oder lokales Ziel ist gesperrt: {host}")
