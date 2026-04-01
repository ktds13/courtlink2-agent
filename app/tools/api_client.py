"""
api_client.py — Shared HTTPS client for CourtLink2.Management API.

Reads connection settings from environment:
    COURTLINK_API_URL       — base URL, e.g. https://localhost:5055
    COURTLINK_CERT_PATH     — path to client certificate: PFX file OR PEM cert file
    COURTLINK_KEY_PATH      — path to PEM private key (only needed when CERT is a PEM, not PFX)
    COURTLINK_CERT_PASSWORD — password for PFX file (leave empty if none)
    COURTLINK_SSL_VERIFY    — "false" to disable TLS verification (dev only)

Certificate formats supported:
    PFX  — set COURTLINK_CERT_PATH to the .pfx file and COURTLINK_CERT_PASSWORD if needed.
           The PFX is extracted to temporary PEM files in memory for httpx.
    PEM  — set COURTLINK_CERT_PATH to the .pem cert and COURTLINK_KEY_PATH to the .pem key.
"""

import os
import json as _json
import tempfile
from pathlib import Path

import httpx

_BASE_URL = os.environ.get("COURTLINK_API_URL", "https://localhost:5055").rstrip("/")
_CERT_PATH = os.environ.get("COURTLINK_CERT_PATH", "").strip()
_KEY_PATH = os.environ.get("COURTLINK_KEY_PATH", "").strip()
_CERT_PASSWORD = os.environ.get("COURTLINK_CERT_PASSWORD", "").strip() or None
_SSL_VERIFY = os.environ.get("COURTLINK_SSL_VERIFY", "true").lower() != "false"

# Temp PEM files extracted from PFX — kept alive for the process lifetime
_tmp_cert_file: "tempfile.NamedTemporaryFile | None" = None
_tmp_key_file: "tempfile.NamedTemporaryFile | None" = None


def _extract_pfx_to_pem(pfx_path: str, password: str | None) -> tuple[str, str]:
    """
    Extract certificate and private key from a PFX file into temporary PEM files.
    Returns (cert_pem_path, key_pem_path).
    Requires the `cryptography` package.
    """
    global _tmp_cert_file, _tmp_key_file

    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PrivateFormat,
        NoEncryption,
        pkcs12,
    )

    pfx_bytes = Path(pfx_path).read_bytes()
    pwd_bytes = password.encode() if password else None
    private_key, certificate, _ = pkcs12.load_key_and_certificates(pfx_bytes, pwd_bytes)

    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(
        Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()
    )

    # Write to named temp files (delete=False so httpx can read by path)
    _tmp_cert_file = tempfile.NamedTemporaryFile(suffix=".crt.pem", delete=False)
    _tmp_cert_file.write(cert_pem)
    _tmp_cert_file.flush()

    _tmp_key_file = tempfile.NamedTemporaryFile(suffix=".key.pem", delete=False)
    _tmp_key_file.write(key_pem)
    _tmp_key_file.flush()

    return _tmp_cert_file.name, _tmp_key_file.name


def _resolve_cert() -> tuple[str, str] | str | None:
    """
    Resolve the cert config to a value httpx.Client accepts for the `cert` parameter:
      - (cert_path, key_path) tuple for separate PEM files or PFX extraction
      - single path string for a combined PEM
      - None if no cert is configured
    """
    if not _CERT_PATH:
        return None

    # PFX file — extract to temp PEM files
    if _CERT_PATH.lower().endswith(".pfx") or _CERT_PATH.lower().endswith(".p12"):
        cert_pem, key_pem = _extract_pfx_to_pem(_CERT_PATH, _CERT_PASSWORD)
        return (cert_pem, key_pem)

    # Separate PEM cert + key
    if _KEY_PATH:
        return (_CERT_PATH, _KEY_PATH)

    # Combined PEM (cert + key in one file)
    return _CERT_PATH


def _build_client() -> httpx.Client:
    """Build a shared synchronous httpx client with mTLS if cert paths are set."""
    cert = _resolve_cert()

    return httpx.Client(
        base_url=_BASE_URL,
        cert=cert,
        verify=_SSL_VERIFY,
        timeout=15.0,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )


# Module-level singleton — re-created if env changes (e.g. tests)
_client: httpx.Client | None = None


def get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


class ApiError(Exception):
    """Raised when the CourtLink2 API returns a non-2xx response."""

    def __init__(self, status_code: int, method: str, path: str, body: str) -> None:
        self.status_code = status_code
        self.method = method
        self.path = path
        self.body = body
        super().__init__(
            f"HTTP {status_code} {method} {path} — {body[:400] if body else '(empty body)'}"
        )


def _raise_for_status(r: "httpx.Response", method: str, path: str) -> None:
    """Raise ApiError with the response body included, instead of a bare HTTPStatusError."""
    if r.is_error:
        body = r.text or ""
        raise ApiError(r.status_code, method, path, body)


def api_get(path: str, params: dict | None = None) -> dict | list:
    r = get_client().get(path, params=params)
    _raise_for_status(r, "GET", path)
    return r.json()


def api_post(path: str, body: dict | None = None) -> dict | list:
    r = get_client().post(path, content=_json.dumps(body or {}))
    _raise_for_status(r, "POST", path)
    # Some endpoints return 204 No Content
    return r.json() if r.content else {}


def api_put(
    path: str, body: dict | None = None, params: dict | None = None
) -> dict | list:
    r = get_client().put(path, content=_json.dumps(body or {}), params=params)
    _raise_for_status(r, "PUT", path)
    return r.json() if r.content else {}


def api_delete(path: str) -> dict:
    r = get_client().delete(path)
    _raise_for_status(r, "DELETE", path)
    return r.json() if r.content else {}
