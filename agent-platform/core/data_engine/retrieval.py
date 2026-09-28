"""LlamaIndex BM25 adapter and deterministic local demo embeddings."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+|[^\W\x00-\x7f]", text.lower())


class DemoEmbedding(BaseEmbedding):
    """Hashed lexical vectors for offline testing, not semantic quality claims."""

    model_name: str = "demo-lexical-hash-256"

    def _get_text_embedding(self, text: str) -> list[float]:
        vector = [0.0] * 256
        for token in tokenize(text):
            bucket = int.from_bytes(hashlib.sha256(token.encode()).digest()[:2], "big") % 256
            vector[bucket] += 1
        norm = math.sqrt(sum(value * value for value in vector)) or 1
        return [value / norm for value in vector]

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._get_text_embedding(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._get_query_embedding(query)


class LexicalRetriever(BaseRetriever):
    def __init__(self, nodes: list[TextNode], top_k: int = 3, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.nodes = nodes
        self.top_k = top_k
        self.bm25 = BM25Okapi([tokenize(n.text) or ["empty"] for n in nodes])

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        scores = self.bm25.get_scores(tokenize(query_bundle.query_str))
        indices = sorted(range(len(self.nodes)), key=lambda i: float(scores[i]), reverse=True)
        return [
            NodeWithScore(node=self.nodes[i], score=float(scores[i]))
            for i in indices[: self.top_k]
            if scores[i] > 0
        ]
