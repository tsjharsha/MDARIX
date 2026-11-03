"""Prepare the local embedding model cache once, pinned and checked, on a developer machine (servers carry the model
in their image, Dockerfile.api). Nothing at run time downloads it (retrieval/embedding_provider.py).

    python scripts/prepare_embedding_cache.py                 # into MDARIX_EMBEDDING_CACHE_DIR, else ./.model-cache
    python scripts/prepare_embedding_cache.py --check         # only verify: present and the pinned weights (SHA-256)
    python scripts/prepare_embedding_cache.py --cache-dir D   # another folder, e.g. one shared by every worktree

The download is the pinned revision of the Hugging Face repository (LOCAL_EMBEDDING_REPO at LOCAL_EMBEDDING_REVISION),
over the normal, TLS-verified client; the weights are then checked against LOCAL_EMBEDDING_MODEL_SHA256. A worktree
can instead point MDARIX_EMBEDDING_CACHE_DIR at the main checkout's prepared .model-cache (tests/conftest.py does so
when the worktree has none).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrieval.embedding_provider import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    LOCAL_EMBEDDING_REPO,
    LOCAL_EMBEDDING_REVISION,
    local_model_problem,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-dir", default=os.environ.get("MDARIX_EMBEDDING_CACHE_DIR") or str(DEFAULT_CACHE_DIR))
    parser.add_argument("--check", action="store_true", help="only verify the cache, never download")
    args = parser.parse_args()
    if not args.check and local_model_problem(args.cache_dir):
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=LOCAL_EMBEDDING_REPO,
            revision=LOCAL_EMBEDDING_REVISION,
            cache_dir=args.cache_dir,
            allow_patterns=["*.json", "*.onnx", "*.txt"],
        )
        # fastembed loads the cache offline through the "main" ref: point it at the pinned commit (as the image does).
        refs = Path(args.cache_dir) / f"models--{LOCAL_EMBEDDING_REPO.replace('/', '--')}" / "refs"
        refs.mkdir(parents=True, exist_ok=True)
        (refs / "main").write_text(LOCAL_EMBEDDING_REVISION)
    problem = local_model_problem(args.cache_dir)
    print(problem or f"EMBEDDING_CACHE_READY {args.cache_dir} {LOCAL_EMBEDDING_REPO}@{LOCAL_EMBEDDING_REVISION}")
    return 1 if problem else 0


if __name__ == "__main__":
    raise SystemExit(main())
