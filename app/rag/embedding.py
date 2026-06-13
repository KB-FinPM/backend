# EN: Embedding service for document chunk and query vectors.
# KO: 문서 chunk와 검색 쿼리 벡터를 생성하는 임베딩 서비스입니다.

from __future__ import annotations

import asyncio
import hashlib
import re
from functools import lru_cache
from typing import Iterable

import numpy as np

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """Creates embeddings with SentenceTransformer and deterministic fallback."""

    def __init__(self) -> None:
        self.model_name = settings.EMBEDDING_MODEL_NAME.strip()
        self.dimension = max(int(settings.EMBEDDING_DIMENSIONS or 1024), 1)
        self.normalize = bool(settings.EMBEDDING_NORMALIZE)
        self._model = None
        self._model_lock = asyncio.Lock()

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0] if vectors else self._fallback_embedding(text)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        normalized_texts = [str(text or "").strip() for text in texts]
        if not normalized_texts:
            return []

        model = await self._get_model()
        if model is None:
            return [self._fallback_embedding(text) for text in normalized_texts]

        def _encode() -> list[list[float]]:
            encoded = model.encode(
                normalized_texts,
                normalize_embeddings=self.normalize,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            if isinstance(encoded, np.ndarray):
                rows = encoded.tolist()
            else:
                rows = [list(row) for row in encoded]
            return [self._normalize_dimension(row) for row in rows]

        try:
            return await asyncio.to_thread(_encode)
        except Exception as exc:
            logger.warning(
                "[Embedding] model encode failed, falling back to hash embeddings | "
                f"model={self.model_name} | error={exc}"
            )
            return [self._fallback_embedding(text) for text in normalized_texts]

    async def _get_model(self):
        if self._model is not None:
            return self._model

        async with self._model_lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(
                    "[Embedding] loading model | "
                    f"model={self.model_name} | dimension={self.dimension}"
                )
                self._model = SentenceTransformer(self.model_name)
            except Exception as exc:
                logger.warning(
                    "[Embedding] model load failed, using fallback hashing | "
                    f"model={self.model_name} | error={exc}"
                )
                self._model = None
            return self._model

    def _fallback_embedding(self, text: str) -> list[float]:
        tokens = re.findall(r"[0-9A-Za-z가-힣]+", str(text or "").lower())
        if not tokens:
            return [0.0] * self.dimension

        vector = np.zeros(self.dimension, dtype=np.float32)
        for position, token in enumerate(tokens, start=1):
            index = self._stable_index(token)
            vector[index] += 1.0 + (position % 7) * 0.1

        if self.normalize:
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector = vector / norm
        return [float(value) for value in vector.tolist()]

    def _normalize_dimension(self, values: Iterable[float]) -> list[float]:
        vector = np.asarray(list(values), dtype=np.float32)
        if vector.size > self.dimension:
            vector = vector[: self.dimension]
        elif vector.size < self.dimension:
            vector = np.pad(vector, (0, self.dimension - vector.size))
        if self.normalize:
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector = vector / norm
        return [float(value) for value in vector.tolist()]

    @lru_cache(maxsize=4096)
    def _stable_index(self, token: str) -> int:
        digest = hashlib.sha1(token.encode("utf-8")).hexdigest()
        return int(digest, 16) % self.dimension


embedding_service = EmbeddingService()
