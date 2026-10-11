import hashlib
import math
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

from backend.app.db.models.retrieval_intelligence import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_MODEL_VERSION,
    EMBEDDING_PIPELINE_VERSION,
    EMBEDDING_PROVIDER,
    LOCAL_EMBEDDING_DIMENSION,
    LOCAL_EMBEDDING_MODEL,
    LOCAL_EMBEDDING_MODEL_VERSION,
    LOCAL_EMBEDDING_PIPELINE_VERSION,
    LOCAL_EMBEDDING_PROVIDER,
)


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9]+")
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / ".model-cache"


@dataclass(frozen=True)
class EmbeddingMetadata:
    provider: str
    model: str
    model_version: str
    dimension: int
    pipeline_version: str
    distance_metric: str = "cosine"


class DeterministicEmbeddingProvider:
    """Local deterministic embedding provider for controlled R1 retrieval tests."""

    def model_metadata(self) -> EmbeddingMetadata:
        return EmbeddingMetadata(
            provider=EMBEDDING_PROVIDER,
            model=EMBEDDING_MODEL,
            model_version=EMBEDDING_MODEL_VERSION,
            dimension=EMBEDDING_DIMENSION,
            pipeline_version=EMBEDDING_PIPELINE_VERSION,
        )

    def embed_text(self, text: str) -> list[float]:
        if "EMBEDDING_FAIL" in text:
            raise ValueError("Controlled embedding failure marker encountered.")

        vector = [0.0] * EMBEDDING_DIMENSION
        tokens = TOKEN_PATTERN.findall((text or "").lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % EMBEDDING_DIMENSION
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 16) / 16.0
            vector[index] += sign * weight

        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude == 0:
            return vector
        return [round(v / magnitude, 8) for v in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(text)


class EmbeddingUnavailable(RuntimeError):
    """The local language model could not be loaded (not downloaded yet and no network, or a broken cache)."""


class LocalModelEmbeddingProvider:
    """A real language-model embedding (bge-small-en-v1.5, ONNX on CPU). Evidence text never leaves the server."""

    _model = None
    _lock = threading.Lock()

    def model_metadata(self) -> EmbeddingMetadata:
        return EmbeddingMetadata(
            provider=LOCAL_EMBEDDING_PROVIDER,
            model=LOCAL_EMBEDDING_MODEL,
            model_version=LOCAL_EMBEDDING_MODEL_VERSION,
            dimension=LOCAL_EMBEDDING_DIMENSION,
            pipeline_version=LOCAL_EMBEDDING_PIPELINE_VERSION,
        )

    @classmethod
    def _load(cls):
        if cls._model is not None:
            return cls._model
        with cls._lock:
            if cls._model is None:
                try:
                    from fastembed import TextEmbedding
                except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
                    from backend.app.runtime_env import is_production_like

                    if is_production_like():
                        # Production-like images must carry both the runtime and the pinned model.  Do not
                        # silently fall back to an install/download path when the optional runtime is absent.
                        raise EmbeddingUnavailable(
                            "The local embedding runtime is not installed; a staging or production server never "
                            "downloads the model (the image carries it)"
                        ) from exc
                    raise EmbeddingUnavailable("fastembed is not installed") from exc
                cache_dir = os.environ.get("MDARIX_EMBEDDING_CACHE_DIR") or str(DEFAULT_CACHE_DIR)
                try:
                    cls._model = TextEmbedding(LOCAL_EMBEDDING_MODEL, cache_dir=cache_dir, local_files_only=True)
                except Exception as missing:
                    from backend.app.runtime_env import is_production_like

                    if is_production_like():
                        # The image carries the model, pinned and checked (Dockerfile.api, config_check): a server
                        # never fetches model weights from the internet, where they could be swapped.
                        raise EmbeddingUnavailable(
                            f"Local embedding model is not in {cache_dir}; a staging or production server never "
                            "downloads it (the image carries it)"
                        ) from missing
                    # First use on this machine: download once into the cache, then it works offline.
                    try:
                        cls._model = TextEmbedding(LOCAL_EMBEDDING_MODEL, cache_dir=cache_dir)
                    except Exception as exc:
                        raise EmbeddingUnavailable(f"Local embedding model could not be loaded: {exc}") from exc
        return cls._model

    @staticmethod
    def _rounded(vector) -> list[float]:
        return [round(float(value), 8) for value in vector]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        return [self._rounded(vector) for vector in model.passage_embed([text or "" for text in texts])]

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        return self._rounded(next(iter(model.query_embed([text or ""]))))


EmbeddingProvider = DeterministicEmbeddingProvider | LocalModelEmbeddingProvider

# SHA-256 of model_optimized.onnx at the pinned revision of Qdrant/bge-small-en-v1.5-onnx-Q (Dockerfile.api,
# EMBEDDING_REVISION). Change both together, and re-index evidence when the weights change.
LOCAL_EMBEDDING_MODEL_SHA256 = "51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431"


def local_model_problem(cache_dir: str | None = None) -> str | None:
    """Why the local embedding model in the cache is not the pinned one (None when it is): missing, or its weights
    differ from the checksum this build was tested with. Run by config_check on staging and production."""
    import hashlib
    from pathlib import Path

    root = Path(cache_dir or os.environ.get("MDARIX_EMBEDDING_CACHE_DIR") or DEFAULT_CACHE_DIR)
    candidates = sorted(root.glob("models--*/snapshots/*/model_optimized.onnx")) if root.is_dir() else []
    if not candidates:
        return (
            f"The local embedding model is not in {root} (MDARIX_EMBEDDING_CACHE_DIR): the image carries it, and a "
            "server never downloads it"
        )
    digest = hashlib.sha256()
    with candidates[-1].open("rb") as weights:
        for chunk in iter(lambda: weights.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != LOCAL_EMBEDDING_MODEL_SHA256:
        return f"The local embedding model in {root} is not the pinned one (checksum differs): rebuild the image"
    return None


def active_embedding_provider() -> EmbeddingProvider:
    """MDARIX_EMBEDDING_PROVIDER: "local" (default, the language model) or "deterministic" (word hashes, tests)."""
    choice = (os.environ.get("MDARIX_EMBEDDING_PROVIDER") or "local").strip().lower()
    if choice == "deterministic":
        return DeterministicEmbeddingProvider()
    return LocalModelEmbeddingProvider()


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
