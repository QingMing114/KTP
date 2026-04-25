"""Basic reranking placeholder for retrieved chunks."""

from __future__ import annotations

import re
from typing import Any

from services.rag_service.schemas import RetrievedChunk


class BasicReranker:
    """Apply lightweight lexical and metadata-aware boosts to retrieval scores."""

    def rerank(
        self,
        *,
        query: str,
        results: list[RetrievedChunk],
        top_k: int,
        task_type: str | None = None,
        region: str | None = None,
        crop_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Rerank retrieved chunks using lightweight heuristics."""
        query_tokens = self._tokenize(query)
        context_tokens = {
            token
            for value in [task_type, region, crop_type, self._flatten_context(context or {})]
            if value
            for token in self._tokenize(str(value))
        }

        reranked: list[RetrievedChunk] = []
        for result in results:
            text_tokens = self._tokenize(result.text)
            metadata_tokens = self._tokenize(self._flatten_context(result.metadata))
            overlap_boost = 0.01 * len(query_tokens & text_tokens)
            context_boost = 0.03 * len(context_tokens & (text_tokens | metadata_tokens))
            reranked.append(
                result.model_copy(
                    update={
                        "score": round(float(result.score) + overlap_boost + context_boost, 6)
                    }
                )
            )

        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked[:top_k]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text.lower())}

    @staticmethod
    def _flatten_context(payload: Any) -> str:
        if isinstance(payload, dict):
            return " ".join(
                f"{key} {BasicReranker._flatten_context(value)}"
                for key, value in payload.items()
            )
        if isinstance(payload, list):
            return " ".join(BasicReranker._flatten_context(item) for item in payload)
        return str(payload)
