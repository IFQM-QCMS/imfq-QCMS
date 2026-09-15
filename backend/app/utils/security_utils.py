"""
Security validation utilities for QCMS Enterprise.
Provides safeguards against SSRF (Server-Side Request Forgery), path traversal,
and input tampering.
"""

import os
import socket
import ipaddress
from urllib.parse import urlparse
from typing import Tuple, Optional


def is_safe_webhook_url(url: str) -> Tuple[bool, str]:
    """
    Validates a URL against Server-Side Request Forgery (SSRF).
    Guarantees:
      1. Scheme must strictly be http or https
      2. Hostname must be non-empty and resolve to a valid IP
      3. IP must NOT be loopback (127.0.0.0/8, ::1)
      4. IP must NOT be private (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
      5. IP must NOT be link-local / cloud metadata (169.254.0.0/16, fe80::/10)
      6. IP must NOT be reserved, multicast, or unspecified (0.0.0.0/8)
    """
    if not url or not isinstance(url, str):
        return False, "URL is required and must be a string."

    url = url.strip()
    if not url:
        return False, "URL cannot be empty."

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, "Only HTTP and HTTPS protocols are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must contain a valid destination hostname."

    lower_host = hostname.lower()
    if lower_host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Localhost addresses are strictly forbidden."

    # Prevent common cloud metadata DNS or numeric representations
    if "169.254" in lower_host or "metadata.google.internal" in lower_host:
        return False, "Cloud instance metadata endpoints are strictly forbidden."

    try:
        # Resolve all IPv4 and IPv6 addresses for the hostname
        addr_infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == 'https' else 80))
        if not addr_infos:
            return False, "Unable to resolve destination hostname."

        for addr_info in addr_infos:
            ip_str = addr_info[4][0]
            ip = ipaddress.ip_address(ip_str)

            if ip.is_loopback:
                return False, "Destination IP resolves to a loopback address."
            if ip.is_private:
                return False, "Destination IP resolves to a private network address."
            if ip.is_link_local:
                return False, "Destination IP resolves to a link-local address."
            if ip.is_reserved:
                return False, "Destination IP resolves to a reserved network address."
            if ip.is_multicast:
                return False, "Destination IP resolves to a multicast address."
            if ip.is_unspecified:
                return False, "Destination IP resolves to an unspecified address."

    except (socket.gaierror, ValueError) as e:
        return False, f"Failed to resolve hostname: {e}"

    return True, ""


def safe_resolve_path(base_dir: str, rel_path: str) -> Optional[str]:
    """
    Resolves rel_path against base_dir and ensures the target file is strictly
    contained within base_dir, preventing directory traversal attacks.
    """
    if not base_dir or not rel_path:
        return None

    # Normalize path separators and remove leading slashes
    clean_rel = os.path.normpath(rel_path.replace("\\", "/")).lstrip("/\\")
    if not clean_rel or clean_rel.startswith(".."):
        return None

    base_abs = os.path.abspath(base_dir)
    target_abs = os.path.abspath(os.path.join(base_abs, clean_rel))

    # Verify target_abs is inside base_abs using commonpath
    try:
        if os.path.commonpath([base_abs, target_abs]) == base_abs:
            return target_abs
    except (ValueError, Exception):
        return None

    return None
