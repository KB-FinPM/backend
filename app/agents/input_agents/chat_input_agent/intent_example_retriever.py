"""In-memory curated intent example retrieval.

This is separate from document RAG/vector DB by design. It uses a tiny
char n-gram similarity index over reviewed command examples.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .korean_command_normalizer import KoreanCommandNormalizer


DEFAULT_EXAMPLE_PATH = Path(__file__).with_name("intent_examples.json")


@dataclass(frozen=True)
class IntentExampleMatch:
    example_id: str
    score: float
    intent: str
    polarity: str
    payload: dict[str, Any]

    @property
    def artifact_type(self) -> str | None:
        return self.payload.get("artifact_type")

    @property
    def schedule_action(self) -> str | None:
        return self.payload.get("schedule_action")

    def to_public_dict(self) -> dict[str, Any]:
        return {"id": self.example_id, "score": round(self.score, 3)}


class IntentExampleRetriever:
    def __init__(
        self,
        *,
        examples: list[dict[str, Any]] | None = None,
        normalizer: KoreanCommandNormalizer | None = None,
        example_path: Path = DEFAULT_EXAMPLE_PATH,
    ) -> None:
        self.normalizer = normalizer or KoreanCommandNormalizer()
        raw_examples = examples if examples is not None else self._load_examples(example_path)
        self.examples = [self._prepare_example(example) for example in raw_examples]

    async def retrieve(
        self,
        normalized_query: str,
        *,
        top_k: int = 3,
    ) -> list[IntentExampleMatch]:
        query = self.normalizer.normalize(normalized_query).normalized_text
        scored = [
            IntentExampleMatch(
                example_id=str(example["id"]),
                score=self._score(query, str(example["normalized_text"])),
                intent=str(example["intent"]),
                polarity=str(example.get("polarity") or "positive"),
                payload=example,
            )
            for example in self.examples
        ]
        scored.sort(key=lambda match: match.score, reverse=True)
        return [match for match in scored[:top_k] if match.score > 0]

    def _load_examples(self, example_path: Path) -> list[dict[str, Any]]:
        return json.loads(example_path.read_text(encoding="utf-8"))

    def _prepare_example(self, example: dict[str, Any]) -> dict[str, Any]:
        normalized = self.normalizer.normalize(str(example.get("text") or ""))
        return {**example, "normalized_text": normalized.normalized_text}

    def _score(self, query: str, example: str) -> float:
        compact_query = self._compact(query)
        compact_example = self._compact(example)
        if not compact_query or not compact_example:
            return 0.0
        if compact_query == compact_example:
            return 1.0
        if compact_query in compact_example or compact_example in compact_query:
            shorter = min(len(compact_query), len(compact_example))
            longer = max(len(compact_query), len(compact_example))
            return max(0.88, shorter / longer)

        bigram_score = self._dice(self._ngrams(compact_query, 2), self._ngrams(compact_example, 2))
        trigram_score = self._dice(self._ngrams(compact_query, 3), self._ngrams(compact_example, 3))
        return round((bigram_score * 0.45) + (trigram_score * 0.55), 4)

    def _compact(self, text: str) -> str:
        return "".join(str(text or "").lower().split())

    def _ngrams(self, text: str, size: int) -> set[str]:
        if len(text) <= size:
            return {text}
        return {text[index : index + size] for index in range(len(text) - size + 1)}

    def _dice(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return (2 * len(left & right)) / (len(left) + len(right))
