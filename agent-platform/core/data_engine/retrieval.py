"""LlamaIndex BM25 lexical retrieval adapter."""

from __future__ import annotations

import re
from typing import Any

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+|[^\W\x00-\x7f]", text.lower())


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
