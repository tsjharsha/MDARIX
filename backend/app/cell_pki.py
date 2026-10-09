"""Certificates for the platform-cell link (ADR-014).

The platform runs a small certificate authority of its own. A cell generates a key and a certificate signing
request at enrollment; the platform signs it once, in exchange for the one-time enrollment token, and from then on
the cell presents the certificate (mutual TLS at the platform's front door) together with its credential. The
authority's key lives in files the platform's API reads (``MDARIX_PLATFORM_CA_KEY_FILE``,
``MDARIX_PLATFORM_CA_CERT_FILE``); nothing here stores a private key in a database.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from backend.app.cell_packages import PackageError

CA_KEY_SETTING = "MDARIX_PLATFORM_CA_KEY_FILE"
CA_CERT_SETTING = "MDARIX_PLATFORM_CA_CERT_FILE"


def _private_key_pem(key) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")


def generate_key() -> str:
    """A new EC P-256 private key as PEM."""
    return _private_key_pem(ec.generate_private_key(ec.SECP256R1()))


def generate_ca(common_name: str = "MDARIX Platform CA", days: int = 3650) -> tuple[str, str]:
    """A self-signed certificate authority: (private key PEM, certificate PEM)."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
        .sign(key, hashes.SHA256())
    )
    return _private_key_pem(key), certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


def csr_pem(key_pem: str, common_name: str, organization: str = "MDARIX tenant cell") -> str:
    key = serialization.load_pem_private_key(key_pem.encode("ascii"), password=None)
    request = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
                ]
            )
        )
        .sign(key, hashes.SHA256())
    )
    return request.public_bytes(serialization.Encoding.PEM).decode("ascii")


def sign_csr(request_pem: str, ca_key_pem: str, ca_cert_pem: str, *, common_name: str, days: int = 365) -> str:
    """The cell's certificate: the request's key under the platform's authority, subject fixed to ``common_name``."""
    try:
        request = x509.load_pem_x509_csr(request_pem.encode("ascii"))
    except ValueError as exc:
        raise PackageError("CSR_FORMAT") from exc
    if not request.is_signature_valid:
        raise PackageError("CSR_SIGNATURE")
    ca_key = serialization.load_pem_private_key(ca_key_pem.encode("ascii"), password=None)
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode("ascii"))
    now = dt.datetime.now(dt.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(ca_cert.subject)
        .public_key(request.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


def fingerprint(certificate_pem: str) -> str:
    """SHA-256 of the certificate's DER bytes, as a lower-case hex string (what the front door forwards)."""
    certificate = x509.load_pem_x509_certificate(certificate_pem.encode("ascii"))
    return hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()


def certificate_common_name(certificate_pem: str) -> str:
    certificate = x509.load_pem_x509_certificate(certificate_pem.encode("ascii"))
    return certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value


def load_platform_ca() -> tuple[str, str]:
    """The platform's authority from its two files, or PackageError when they are not configured."""
    key_file, cert_file = os.getenv(CA_KEY_SETTING, "").strip(), os.getenv(CA_CERT_SETTING, "").strip()
    if not key_file or not cert_file:
        raise PackageError(f"{CA_KEY_SETTING} and {CA_CERT_SETTING} are not configured")
    try:
        with open(key_file, encoding="ascii") as handle:
            key_pem = handle.read()
        with open(cert_file, encoding="ascii") as handle:
            cert_pem = handle.read()
    except OSError as exc:
        raise PackageError(f"The platform's certificate authority files cannot be read ({type(exc).__name__})") from exc
    return key_pem, cert_pem


def platform_ca_problem() -> str | None:
    """Why the configured authority cannot sign (None when it can)."""
    try:
        key_pem, cert_pem = load_platform_ca()
        serialization.load_pem_private_key(key_pem.encode("ascii"), password=None)
        certificate = x509.load_pem_x509_certificate(cert_pem.encode("ascii"))
    except PackageError as exc:
        return str(exc)
    except ValueError:
        return "The platform's certificate authority files are not a PEM key and certificate"
    if certificate.not_valid_after_utc <= dt.datetime.now(dt.timezone.utc):
        return "The platform's certificate authority certificate has expired"
    return None
