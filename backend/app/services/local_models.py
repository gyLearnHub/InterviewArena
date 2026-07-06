import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [item.lower() for item in TOKEN_PATTERN.findall(text) if item.strip()]


class LocalEmbeddingModel:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        model_path: str | None = None,
        device: str | None = None,
    ) -> None:
        settings = settings or get_settings()
        self.model_path = model_path or settings.embedding_model_path
        self.device = device or settings.embedding_device
        if not self.model_path:
            raise RuntimeError("embedding_model_path_missing")
        try:
            module = __import__("sentence_transformers", fromlist=["SentenceTransformer"])
            _ = module.SentenceTransformer
        except Exception as exc:  # pragma: no cover - depends on local runtime
            raise RuntimeError("sentence_transformers_unavailable") from exc

        self._model: Any = _sentence_transformer(self.model_path, self.device)
        self.version = f"sentence-transformers:{Path(self.model_path).name}"

    def embed(self, text: str) -> list[float]:
        embeddings = self._model.encode([text], normalize_embeddings=True)
        return [float(value) for value in embeddings[0]]


class LocalReranker:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        model_path: str | None = None,
        device: str | None = None,
    ) -> None:
        settings = settings or get_settings()
        self.model_path = model_path or settings.reranker_model_path
        self.device = device or settings.reranker_device
        if not self.model_path:
            raise RuntimeError("reranker_model_path_missing")
        try:
            module = __import__("sentence_transformers", fromlist=["CrossEncoder"])
            _ = module.CrossEncoder
        except Exception as exc:  # pragma: no cover - depends on local runtime
            raise RuntimeError("sentence_transformers_unavailable") from exc

        self._model: Any = _cross_encoder(self.model_path, self.device)
        self.version = f"cross-encoder:{Path(self.model_path).name}"

    def score(self, query: str, content: str, confidence: float = 0.0) -> float:
        _ = confidence
        scores = self._model.predict([(query, content)])
        return float(scores[0])


@lru_cache(maxsize=4)
def _sentence_transformer(model_path: str, device: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_path, device=device)


@lru_cache(maxsize=4)
def _cross_encoder(model_path: str, device: str) -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_path, device=device)
