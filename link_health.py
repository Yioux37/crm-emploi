"""Vérification ponctuelle d'un lien, sans supprimer une annonce sur un 403/429."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit
import requests


def public_url(url: str) -> bool:
    """Refuse IP internes, localhost et hôtes sans DNS public (anti-SSRF basique)."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            return False
        host = parts.hostname.lower()
        if "." not in host or host.endswith((".local", ".internal", ".test")):
            return False
        addresses = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
        if not addresses:
            return False
        for item in addresses:
            ip = ipaddress.ip_address(item[4][0])
            if not ip.is_global:
                return False
        return True
    except (OSError, ValueError, OverflowError):
        return False


def check_link(url: str) -> str:
    """Accessible / Indisponible / À vérifier; aucune suppression automatique."""
    if not url or not public_url(url):
        return "À vérifier"
    current = url
    try:
        with requests.Session() as session:
            # Redirections vérifiées une par une; requêtes en streaming sans corps téléchargé.
            for _ in range(5):
                if not public_url(current):
                    return "À vérifier"
                resp = session.head(current, allow_redirects=False, timeout=(4, 7))
                with resp:
                    if resp.status_code == 405:
                        resp = session.get(current, allow_redirects=False, timeout=(4, 7), stream=True)
                    with resp:
                        code = resp.status_code
                        location = resp.headers.get("Location")
                        if code in (301, 302, 303, 307, 308) and location:
                            current = urljoin(current, location)
                            continue
                        if 200 <= code < 400:
                            return "Accessible"
                        if code in (404, 410):
                            return "Indisponible"
                        return "À vérifier"  # Login / CAPTCHA / rate-limit ≠ lien mort
    except requests.RequestException:
        return "À vérifier"
    return "À vérifier"
