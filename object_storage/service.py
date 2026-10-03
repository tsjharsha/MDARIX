"""Tenant-safe object storage with local and S3-compatible backends.

The local backend is intentionally retained for development.  Production must
select ``MDARIX_OBJECT_STORAGE_PROVIDER=s3`` and provide an S3-compatible
endpoint/bucket and credentials.  Object keys and signed URLs never cross a
tenant prefix.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
import time
import base64
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode


class StorageError(RuntimeError):
    pass


class ObjectStorageService:
    def __init__(self, root: str | None = None, *, audit=None):
        self.provider = os.getenv("MDARIX_OBJECT_STORAGE_PROVIDER", "local").lower()
        self.max_object_bytes = int(os.getenv("MDARIX_OBJECT_STORAGE_MAX_BYTES", str(10 * 1024 * 1024)))
        self.tenant_quota_bytes = int(os.getenv("MDARIX_OBJECT_STORAGE_TENANT_QUOTA_BYTES", str(100 * 1024 * 1024)))
        self.signing_secret = os.getenv("MDARIX_OBJECT_STORAGE_SIGNING_SECRET")
        self.encryption_key = os.getenv("MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY")
        self.retention_days = int(os.getenv("MDARIX_OBJECT_STORAGE_RETENTION_DAYS", "2555"))
        if self.provider == "s3":
            try:
                import boto3
            except ImportError as exc:
                raise StorageError("S3 provider requires the boto3 dependency") from exc
            self.bucket = os.environ["MDARIX_OBJECT_STORAGE_BUCKET"]
            self.client = boto3.client(
                "s3",
                endpoint_url=os.getenv("MDARIX_OBJECT_STORAGE_ENDPOINT"),
                region_name=os.getenv("MDARIX_OBJECT_STORAGE_REGION", "us-east-1"),
                aws_access_key_id=os.getenv("MDARIX_OBJECT_STORAGE_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("MDARIX_OBJECT_STORAGE_SECRET_KEY"),
            )
        elif self.provider == "local":
            self.root = Path(root or os.getenv("MDARIX_OBJECT_STORAGE_ROOT", ".mdarix-object-storage"))
            self.root.mkdir(parents=True, exist_ok=True)
        else:
            raise StorageError(f"Unsupported object storage provider: {self.provider}")
        self.audit = audit

    @staticmethod
    def _tenant_key(tenant_id: str, key: str) -> str:
        tenant = str(tenant_id).strip()
        name = str(key).replace("\\", "/").lstrip("/")
        path = PurePosixPath(name)
        if not tenant or tenant in {".", ".."} or any(part in {"", ".", ".."} for part in path.parts):
            raise StorageError("Invalid tenant or object key")
        return f"{tenant}/{path.as_posix()}"

    @staticmethod
    def _assert_tenant_key(tenant_id: str, object_key: str) -> str:
        expected_prefix = f"{tenant_id}/"
        if not str(object_key).startswith(expected_prefix):
            raise FileNotFoundError(object_key)
        suffix = str(object_key)[len(expected_prefix) :]
        if not suffix or any(part in {"", ".", ".."} for part in PurePosixPath(suffix).parts):
            raise FileNotFoundError(object_key)
        return str(object_key)

    def _tenant_usage(self, tenant_id: str) -> int:
        if self.provider == "local":
            base = self.root / str(tenant_id)
            return sum(p.stat().st_size for p in base.rglob("*") if p.is_file()) if base.exists() else 0
        return 0  # S3 quota is enforced by the durable attachment metadata layer.

    def _audit(self, action: str, tenant_id: str, object_key: str, **details):
        if self.audit:
            self.audit(action, tenant_id, object_key, details)

    def put(
        self,
        tenant_id: str,
        key: str,
        content: bytes,
        *,
        content_type: str = "application/octet-stream",
        retention_until: datetime | None = None,
        internal: bool = False,
    ) -> dict:
        """Store one object under the tenant's prefix. ``internal=True`` is for files MDARIX generates itself
        (reports, data exports): they are not virus-scanned and not held to the upload size and quota limits, but are
        encrypted and tenant-scoped like everything else."""
        if not internal:
            if len(content) > self.max_object_bytes:
                raise StorageError("OBJECT_SIZE_QUOTA_EXCEEDED")
            if not self.scan(content, content_type):
                raise StorageError("MALWARE_SCAN_REJECTED")
        object_key = self._tenant_key(tenant_id, key)
        if (
            not internal
            and self.provider == "local"
            and self._tenant_usage(tenant_id) + len(content) > self.tenant_quota_bytes
        ):
            raise StorageError("TENANT_STORAGE_QUOTA_EXCEEDED")
        checksum = hashlib.sha256(content).hexdigest()
        if self.provider == "s3":
            self.client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=content,
                ContentType=content_type,
                ServerSideEncryption=os.getenv("MDARIX_OBJECT_STORAGE_SSE", "AES256"),
                Metadata={
                    "tenant-id": str(tenant_id),
                    "sha256": checksum,
                    **({"retention-until": retention_until.isoformat()} if retention_until else {}),
                },
            )
        else:
            path = self.root / object_key
            path.parent.mkdir(parents=True, exist_ok=True)
            stored = content
            if self.encryption_key:
                try:
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

                    key_bytes = base64.urlsafe_b64decode(self.encryption_key + "=" * (-len(self.encryption_key) % 4))
                    if len(key_bytes) not in {16, 24, 32}:
                        raise ValueError("encryption key must decode to 16, 24, or 32 bytes")
                    nonce = os.urandom(12)
                    stored = b"MDARIXENC1" + nonce + AESGCM(key_bytes).encrypt(nonce, content, object_key.encode())
                except ImportError as exc:
                    raise StorageError("OBJECT_ENCRYPTION_REQUIRES_CRYPTOGRAPHY") from exc
                except Exception as exc:
                    raise StorageError("OBJECT_ENCRYPTION_FAILED") from exc
            path.write_bytes(stored)
            if retention_until:
                path.with_suffix(path.suffix + ".retention").write_text(retention_until.isoformat(), encoding="utf-8")
        self._audit("OBJECT_STORED", str(tenant_id), object_key, size=len(content), checksum=checksum)
        return {
            "tenant_id": str(tenant_id),
            "object_key": object_key,
            "size": len(content),
            "checksum": checksum,
            "content_type": content_type,
            "retention_until": retention_until,
        }

    @staticmethod
    def _clamd_scan(content: bytes) -> bool:
        """Scan with a ClamAV daemon (clamd INSTREAM over TCP). Any failure to get a clean verdict refuses the file."""
        import socket
        import struct

        host = os.getenv("MDARIX_CLAMD_HOST", "").strip()
        port = int(os.getenv("MDARIX_CLAMD_PORT", "3310"))
        try:
            with socket.create_connection(
                (host, port), timeout=float(os.getenv("MDARIX_CLAMD_TIMEOUT_SECONDS", "30"))
            ) as conn:
                conn.sendall(b"zINSTREAM\0")
                for start in range(0, len(content), 65536):
                    chunk = content[start : start + 65536]
                    conn.sendall(struct.pack("!I", len(chunk)) + chunk)
                conn.sendall(struct.pack("!I", 0))
                reply = b""
                while not reply.endswith(b"\0"):
                    part = conn.recv(4096)
                    if not part:
                        break
                    reply += part
        except OSError:
            return False
        return reply.rstrip(b"\0").strip().endswith(b"OK")

    def scan(self, content: bytes, content_type: str) -> bool:
        if os.getenv("MDARIX_CLAMD_HOST", "").strip():
            return self._clamd_scan(content)
        scanner = os.getenv("MDARIX_MALWARE_SCANNER_COMMAND")
        if scanner:
            try:
                result = subprocess.run(
                    scanner.split(),
                    input=content,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=15,
                    check=False,
                )
                return result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                return False
        dangerous_headers = (b"MZ", b"\x7fELF", b"#!")
        if content[:2] in dangerous_headers[:2] or content.startswith(dangerous_headers[2]):
            return False
        return not (content_type == "application/pdf" and b"/JavaScript" in content[:2_000_000])

    def get(self, tenant_id: str, object_key: str) -> bytes:
        expected = self._assert_tenant_key(tenant_id, object_key)
        if self.provider == "s3":
            body = self.client.get_object(Bucket=self.bucket, Key=expected)["Body"].read()
        else:
            path = self.root / expected
            if not path.is_file():
                raise FileNotFoundError(object_key)
            body = path.read_bytes()
            if body.startswith(b"MDARIXENC1"):
                if not self.encryption_key:
                    raise StorageError("OBJECT_ENCRYPTION_KEY_NOT_CONFIGURED")
                try:
                    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

                    key_bytes = base64.urlsafe_b64decode(self.encryption_key + "=" * (-len(self.encryption_key) % 4))
                    nonce, ciphertext = body[10:22], body[22:]
                    body = AESGCM(key_bytes).decrypt(nonce, ciphertext, expected.encode())
                except Exception as exc:
                    raise StorageError("OBJECT_DECRYPTION_FAILED") from exc
        self._audit("OBJECT_READ", str(tenant_id), expected, size=len(body))
        return body

    def signed_url(self, tenant_id: str, object_key: str, *, expires_seconds: int = 300) -> str:
        expected = self._assert_tenant_key(tenant_id, object_key)
        if expires_seconds < 1 or expires_seconds > 3600:
            raise StorageError("INVALID_SIGNED_URL_REQUEST")
        if self.provider == "s3":
            return self.client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": expected}, ExpiresIn=expires_seconds
            )
        if not self.signing_secret:
            raise StorageError("SIGNED_URL_SECRET_NOT_CONFIGURED")
        expires = int(time.time()) + expires_seconds
        signature = hmac.new(self.signing_secret.encode(), f"{expected}:{expires}".encode(), hashlib.sha256).hexdigest()
        self._audit("OBJECT_SIGNED_URL_CREATED", str(tenant_id), expected, expires_at=expires)
        return "local://object?" + urlencode({"key": expected, "expires": expires, "signature": signature})

    def verify_signed_url(self, tenant_id: str, signed_url: str) -> str:
        """Validate a development signed URL and return its tenant-scoped key."""
        if self.provider != "local" or not signed_url.startswith("local://object?"):
            raise StorageError("SIGNED_URL_VERIFICATION_UNSUPPORTED")
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(signed_url).query)
        key = query.get("key", [""])[0]
        expires = int(query.get("expires", ["0"])[0])
        signature = query.get("signature", [""])[0]
        expected = self._assert_tenant_key(tenant_id, key)
        if expires < int(time.time()) or not self.signing_secret:
            raise StorageError("SIGNED_URL_EXPIRED")
        expected_signature = hmac.new(
            self.signing_secret.encode(), f"{expected}:{expires}".encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise StorageError("INVALID_SIGNED_URL")
        return expected

    def delete_expired(self, *, now: datetime | None = None) -> int:
        """Delete locally retained objects; S3 lifecycle rules handle production retention."""
        if self.provider != "local":
            return 0
        now = (now or datetime.now()).timestamp()
        deleted = 0
        for marker in self.root.glob("**/*.retention"):
            try:
                expires = datetime.fromisoformat(marker.read_text(encoding="utf-8")).timestamp()
                if expires <= now:
                    object_path = Path(str(marker)[: -len(".retention")])
                    if object_path.is_file():
                        object_path.unlink()
                    marker.unlink()
                    deleted += 1
            except (OSError, ValueError):
                continue
        return deleted

    def delete(self, tenant_id: str, object_key: str) -> None:
        expected = self._assert_tenant_key(tenant_id, object_key)
        if self.provider == "s3":
            self.client.delete_object(Bucket=self.bucket, Key=expected)
        else:
            path = self.root / expected
            if path.exists():
                path.unlink()
        self._audit("OBJECT_DELETED", str(tenant_id), expected)

    def list_tenant_objects(self, tenant_id: str) -> list[str]:
        """Every stored object key of one tenant (``<tenant>/...``)."""
        prefix = self._tenant_key(tenant_id, "x")[:-1]
        if self.provider == "s3":
            keys: list[str] = []
            for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
                keys.extend(item["Key"] for item in page.get("Contents", []))
            return keys
        base = self.root / str(tenant_id)
        if not base.is_dir():
            return []
        return sorted(
            f"{prefix}{path.relative_to(base).as_posix()}"
            for path in base.rglob("*")
            if path.is_file() and not path.name.endswith(".retention")
        )

    def delete_tenant(self, tenant_id: str) -> int:
        """Delete every object of one tenant (organization offboarding or trial deletion). Returns how many.

        On a versioned S3 bucket this leaves delete markers; the bucket's noncurrent-version expiry rule removes the
        old versions (docs/runbooks/DATA_REQUESTS.md)."""
        keys = self.list_tenant_objects(tenant_id)
        if self.provider == "s3":
            for start in range(0, len(keys), 1000):
                batch = [{"Key": key} for key in keys[start : start + 1000]]
                response = self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": batch, "Quiet": True})
                if response.get("Errors"):
                    raise StorageError(f"OBJECT_DELETE_FAILED:{len(response['Errors'])}")
        else:
            import shutil

            base = self.root / str(tenant_id)
            if base.is_dir():
                shutil.rmtree(base)
        if self.list_tenant_objects(tenant_id):
            raise StorageError("OBJECT_DELETE_INCOMPLETE")
        self._audit("TENANT_OBJECTS_DELETED", str(tenant_id), f"{tenant_id}/", count=len(keys))
        return len(keys)
