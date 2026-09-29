"""Data-engine tests: hybrid index build/query, tool adapters, compression, retrieval."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import StructuredTool
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from core.data_engine.compression import summarize_texts
from core.data_engine.engine import (
    as_langchain_tool,
    as_mcp_tool_spec,
    build_query_engine,
    format_response,
)
from core.data_engine.retrieval import LexicalRetriever, tokenize
from core.demo import DemoEmbedding

os.environ.setdefault("AGENT_PLATFORM_DEMO", "1")

DOC_ALPHA = """# Alpha Guide

The alpha service stores session tokens in Redis with a 30 minute TTL.
Operators rotate the signing key every Monday at 09:00 UTC.
"""

DOC_BETA = """# Beta Guide

The beta pipeline compresses knowledge documents before indexing.
Hybrid retrieval fuses vector similarity with BM25 lexical ranking.
"""


@pytest.fixture(scope="module")
def docs_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("knowledge")
    (root / "alpha.md").write_text(DOC_ALPHA, encoding="utf-8")
    (root / "beta.md").write_text(DOC_BETA, encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def engine(docs_dir: Path) -> Iterator[Any]:
    yield build_query_engine(docs_dir, top_k=2)


def _parse_sources(payload: str) -> dict[str, Any]:
    data = json.loads(payload)
    assert set(data) == {"answer", "sources"}
    assert isinstance(data["answer"], str)
    assert isinstance(data["sources"], list) and data["sources"]
    return data


def test_build_query_engine_and_format_response(engine: Any, docs_dir: Path) -> None:
    response = engine.query("signing key rotation schedule")
    payload = format_response(response)
    data = _parse_sources(payload)
    files = {s["file"] for s in data["sources"]}
    assert files <= {"alpha.md", "beta.md"}
    assert "alpha.md" in files
    for source in data["sources"]:
        assert set(source) == {"file", "text", "score"}
        assert isinstance(source["text"], str) and source["text"]
        assert isinstance(source["score"], (int, float))


def test_build_query_engine_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_query_engine(tmp_path / "does-not-exist")


def test_build_query_engine_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No non-empty"):
        build_query_engine(tmp_path)


def test_build_query_engine_only_blank_documents(tmp_path: Path) -> None:
    (tmp_path / "blank.md").write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError, match="No non-empty"):
        build_query_engine(tmp_path)


def test_as_langchain_tool(engine: Any) -> None:
    tool = as_langchain_tool(engine)
    assert isinstance(tool, StructuredTool)
    assert tool.name == "hybrid_retrieve"
    assert tool.description
    result = tool.invoke({"query": "session token TTL"})
    data = _parse_sources(result)
    assert any("alpha.md" == s["file"] for s in data["sources"])


async def test_as_langchain_tool_arun(engine: Any) -> None:
    tool = as_langchain_tool(engine)
    result = await tool.ainvoke({"query": "BM25 lexical ranking"})
    data = _parse_sources(result)
    assert any("beta.md" == s["file"] for s in data["sources"])


async def test_as_langchain_tool_blank_query(engine: Any) -> None:
    tool = as_langchain_tool(engine)
    with pytest.raises(ValueError, match="blank"):
        await tool.ainvoke({"query": "   "})


async def test_as_mcp_tool_spec(engine: Any) -> None:
    async def fake_factory(path: str) -> Any:
        assert path
        return engine

    spec = as_mcp_tool_spec(engine_factory=fake_factory)
    assert set(spec) == {"name", "description", "func"}
    assert spec["name"] == "hybrid_retrieve"
    assert isinstance(spec["description"], str) and spec["description"]
    result = await spec["func"]("signing key rotation")
    _parse_sources(result)
    with pytest.raises(ValueError, match="blank"):
        await spec["func"]("")


async def test_summarize_texts_within_limit() -> None:
    texts = ["第一段對話內容", "第二段對話內容"]
    assert await summarize_texts(texts, max_chars=100) == "\n\n".join(texts)


async def test_summarize_texts_skips_blank_entries() -> None:
    assert await summarize_texts(["", "  ", "唯一內容"], max_chars=100) == "唯一內容"


async def test_summarize_texts_truncates_over_limit() -> None:
    texts = ["a" * 400, "b" * 400]
    result = await summarize_texts(texts, max_chars=100)
    assert len(result) <= 100
    assert result.startswith("a")
    assert result.endswith("b")
    assert "[omitted]" in result


async def test_summarize_texts_non_positive_limit() -> None:
    assert await summarize_texts(["anything"], max_chars=0) == ""
    assert await summarize_texts(["anything"], max_chars=-5) == ""


def test_tokenize_mixed_language() -> None:
    assert tokenize("Redis TTL 30") == ["redis", "ttl", "30"]
    assert "簽" in tokenize("輪換簽名金鑰")


def _lexical_retriever() -> LexicalRetriever:
    nodes = [
        TextNode(text="redis session token ttl rotation", metadata={"file_name": "a.md"}),
        TextNode(text="bm25 lexical ranking fusion", metadata={"file_name": "b.md"}),
        TextNode(text="unrelated gardening notes", metadata={"file_name": "c.md"}),
    ]
    return LexicalRetriever(nodes, top_k=2)


def test_lexical_retriever_ranking() -> None:
    retriever = _lexical_retriever()
    results = retriever.retrieve(QueryBundle(query_str="redis token"))
    assert results
    assert all(isinstance(r, NodeWithScore) for r in results)
    assert results[0].node.metadata["file_name"] == "a.md"
    assert all(r.score is not None and r.score > 0 for r in results)
    assert len(results) <= 2
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_lexical_retriever_no_match_returns_empty() -> None:
    retriever = _lexical_retriever()
    assert retriever.retrieve(QueryBundle(query_str="zzzqqq nonexistent")) == []


def test_demo_embedding_deterministic_normalized() -> None:
    import math

    embedding = DemoEmbedding()
    vector = embedding.get_text_embedding("session token ttl")
    assert len(vector) == 256
    assert vector == embedding.get_text_embedding("session token ttl")
    assert vector != embedding.get_text_embedding("totally different content")
    norm = math.sqrt(sum(v * v for v in vector))
    assert norm == pytest.approx(1.0)
