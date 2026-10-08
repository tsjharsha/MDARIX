"""Signed documents between the platform and a tenant cell (ADR-014).

The platform signs what a cell must trust: the enrollment bundle that creates the cell's organization, the licence
that gives it its plan, and later the reference-data, mapping-template and policy packages. A cell pins the
platform's public key at install (``MDARIX_PLATFORM_SIGNING_PUBLIC_KEY``) and refuses anything that does not verify.

Ed25519 over the canonical JSON of the content (sorted keys, no whitespace). The envelope carries the kind, the
content, its SHA-256 and the signature; the private key lives with the release pipeline, never in a cell.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

KINDS = frozenset({"ENROLLMENT", "LICENCE", "REFERENCE_DATA", "MAPPING_TEMPLATE", "POLICY"})
ENVELOPE_VERSION = 1
PUBLIC_KEY_SETTING = "MDARIX_PLATFORM_SIGNING_PUBLIC_KEY"


class PackageError(ValueError):
    """A document that cannot be trusted: wrong shape, wrong kind, digest or signature mismatch."""


def canonical_json(content: dict) -> bytes:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(value: str, name: str, length: int) -> bytes:
    text = (value or "").strip()
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except Exception as exc:
        raise PackageError(f"{name} is not base64") from exc
    if len(raw) != length:
        raise PackageError(f"{name} must decode to {length} bytes")
    return raw


def generate_keypair() -> tuple[str, str]:
    """A new signing key pair as (private, public), both URL-safe base64 of the raw 32 bytes."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    raw_private = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    raw_public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return _encode(raw_private), _encode(raw_public)


def sign(kind: str, content: dict, private_key: str, *, key_id: str = "platform") -> dict:
    """Wrap ``content`` in a signed envelope of ``kind``."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if kind not in KINDS:
        raise PackageError(f"Unknown package kind {kind}")
    body = canonical_json(content)
    signer = Ed25519PrivateKey.from_private_bytes(_decode(private_key, "private key", 32))
    return {
        "kind": kind,
        "version": ENVELOPE_VERSION,
        "key_id": key_id,
        "content": content,
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "signature": _encode(signer.sign(body)),
    }


def verify(envelope: dict, public_key: str, *, kind: str | None = None) -> dict:
    """The content of a signed envelope, once its shape, digest and signature are checked against ``public_key``."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not isinstance(envelope, dict) or envelope.get("version") != ENVELOPE_VERSION:
        raise PackageError("PACKAGE_FORMAT")
    if envelope.get("kind") not in KINDS or (kind is not None and envelope.get("kind") != kind):
        raise PackageError("PACKAGE_KIND")
    content = envelope.get("content")
    if not isinstance(content, dict):
        raise PackageError("PACKAGE_CONTENT")
    body = canonical_json(content)
    if hashlib.sha256(body).hexdigest() != envelope.get("content_sha256"):
        raise PackageError("PACKAGE_DIGEST")
    verifier = Ed25519PublicKey.from_public_bytes(_decode(public_key, PUBLIC_KEY_SETTING, 32))
    try:
        verifier.verify(_decode(str(envelope.get("signature") or ""), "signature", 64), body)
    except (InvalidSignature, PackageError) as exc:
        raise PackageError("PACKAGE_SIGNATURE") from exc
    return content


def platform_public_key() -> str:
    return os.getenv(PUBLIC_KEY_SETTING, "").strip()


def public_key_problem(value: str) -> str | None:
    """Why ``value`` cannot serve as the pinned platform key (None when it can)."""
    if not value:
        return (
            f"{PUBLIC_KEY_SETTING} must be set in a CELL: the platform's package-signing public key (base64, 32 bytes)"
        )
    try:
        _decode(value, PUBLIC_KEY_SETTING, 32)
    except PackageError as exc:
        return str(exc)
    return None
