"""Re-encrypt every stored file with the current object storage encryption key (after a key rotation).

Local object storage only: the files under MDARIX_OBJECT_STORAGE_ROOT, so run it where they are, in the API's container
(``dc run --rm --no-deps api python scripts/reencrypt_object_storage.py``). Each encrypted file is opened with the
keyring (MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY plus MDARIX_OBJECT_STORAGE_ENCRYPTION_KEYS, object_storage/service.py)
and encrypted again with the current key and key ID. The new bytes must open with the current key alone and give the
same content; they are then written to a temporary file next to the original, with its permissions, owner and
modification time, and renamed over it, so a file is always either the old one or the new one. Files already on the
current key are left alone, and so are files stored without encryption and the retention markers. A file that cannot be
opened is reported (its object key, never its content) and left unchanged, and the script then exits 1. Dry run by
default; safe to run again (a temporary file left by an interrupted run is removed).

    python scripts/reencrypt_object_storage.py            # what would change
    python scripts/reencrypt_object_storage.py --apply    # then remove the old key from ..._ENCRYPTION_KEYS
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from object_storage.service import is_encrypted, object_keyring, open_object, seal_object, stored_key_id  # noqa: E402
from security.keyring import KeyringError  # noqa: E402

TEMPORARY_SUFFIX = ".reencrypt-tmp"
RETENTION_SUFFIX = ".retention"


def _on_current_key(body: bytes, object_key: str, ring, current_only) -> bool:
    """Encrypted with the current key ID; or, while the key has no ID, encrypted without one and opened by the current
    key."""
    key_id = stored_key_id(body)
    if ring.current_id is not None:
        return key_id == ring.current_id
    if key_id is not None:
        return False
    try:
        open_object(current_only, object_key, body)
        return True
    except ValueError:
        return False


def _replace(path: Path, data: bytes) -> None:
    """Write ``data`` over ``path`` atomically, keeping its permissions, owner and modification time."""
    before = path.stat()
    temporary = path.with_name(f".{path.name}{TEMPORARY_SUFFIX}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(before.st_mode))
        if hasattr(os, "chown"):
            written = temporary.stat()
            if (written.st_uid, written.st_gid) != (before.st_uid, before.st_gid):
                os.chown(temporary, before.st_uid, before.st_gid)
        os.utime(temporary, ns=(before.st_atime_ns, before.st_mtime_ns))
        if not path.exists():
            raise FileNotFoundError("deleted while being re-encrypted")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def reencrypt(root: Path, *, apply: bool, out=print) -> dict[str, int]:
    """Counts of files re-encrypted (or that would be), already on the current key, not encrypted, and unreadable."""
    ring = object_keyring()
    if ring is None:
        raise SystemExit("MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY is not set: there is no key to re-encrypt with.")
    current_only = replace(ring, older={})
    counts = {"reencrypted": 0, "current": 0, "not_encrypted": 0, "failed": 0, "leftovers": 0}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.endswith(RETENTION_SUFFIX):
            continue
        if path.name.endswith(TEMPORARY_SUFFIX):
            # From an interrupted run: the original beside it was never replaced.
            counts["leftovers"] += 1
            if apply:
                path.unlink(missing_ok=True)
            continue
        object_key = path.relative_to(root).as_posix()
        try:
            body = path.read_bytes()
            if not is_encrypted(body):
                counts["not_encrypted"] += 1
                continue
            if _on_current_key(body, object_key, ring, current_only):
                counts["current"] += 1
                continue
            content = open_object(ring, object_key, body)
            sealed = seal_object(ring, object_key, content)
            if open_object(current_only, object_key, sealed) != content:
                raise ValueError("OBJECT_REENCRYPT_CHECK_FAILED")
            if apply:
                _replace(path, sealed)
        except Exception as exc:
            counts["failed"] += 1
            out(f"UNREADABLE  {object_key}: {type(exc).__name__} {exc}"[:300])
            continue
        counts["reencrypted"] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the re-encrypted files (default: dry run)")
    parser.add_argument(
        "--root",
        default=os.getenv("MDARIX_OBJECT_STORAGE_ROOT", ".mdarix-object-storage"),
        help="the object storage folder (default: MDARIX_OBJECT_STORAGE_ROOT)",
    )
    args = parser.parse_args(argv)
    if os.getenv("MDARIX_OBJECT_STORAGE_PROVIDER", "local").strip().lower() != "local":
        print("Object storage is not local: the provider's own key management encrypts the files. Nothing to do.")
        return 0
    root = Path(args.root)
    if not root.is_dir():
        print(f"{root} is not a folder: run this where the files are (the API's container).")
        return 1
    try:
        counts = reencrypt(root, apply=args.apply)
    except KeyringError as exc:
        print(f"STOP: {exc}. Nothing was changed.")
        return 1
    key_id = object_keyring().current_id or "(no key ID)"
    verb = "Re-encrypted" if args.apply else "Would re-encrypt"
    print(
        f"{verb} {counts['reencrypted']}; already on key {key_id}: {counts['current']}; "
        f"not encrypted (left as they are): {counts['not_encrypted']}; unreadable: {counts['failed']}"
        + (f"; temporary files of an interrupted run: {counts['leftovers']}" if counts["leftovers"] else "")
        + "."
    )
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
