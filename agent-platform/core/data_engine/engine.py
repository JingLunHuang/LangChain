"""Independent LlamaIndex vector + BM25 engine with reciprocal rank fusion."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

DEFAULT_DOCS_PATH_ENV = "AGENT_PLATFORM_DOCS_PATH"
DEFAULT_DOCS_PATH = Path(__file__).resolve().parents[2] / "examples" / "knowledge"
_TOOL_NAME = "hybrid_retrieve"
_TOOL_DESCRIPTION = "檢索本地知識庫：結合向量與 BM25，回傳引用摘錄及來源。"


def configured_models() -> tuple[Any, Any]:
    if os.getenv("AGENT_PLATFORM_DEMO") == "1":
        from llama_index.core.llms import MockLLM

        from core.demo import DemoEmbedding

        return DemoEmbedding(), MockLLM()
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.llms.openai_like import OpenAILike

    key = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")
    if not key:
        raise RuntimeError("Set EMBEDDING_API_KEY and EMBEDDING_MODEL, or AGENT_PLATFORM_DEMO=1")
    base = (
        os.getenv("EMBEDDING_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1"
    )
    model = os.getenv("LLM_MODEL", "")
    embedding = os.getenv("EMBEDDING_MODEL", "")
    if not embedding:
        raise RuntimeError("EMBEDDING_MODEL must be configured")
    from llama_index.core.llms import MockLLM

    summary_llm = (
        OpenAILike(
            model=model,
            api_key=os.environ["LLM_API_KEY"],
            api_base=os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
            is_chat_model=True,
            is_function_calling_model=True,
            context_window=8192,
        )
        if model and os.getenv("LLM_API_KEY")
        else MockLLM()
    )
    return (
        OpenAIEmbedding(model_name=embedding, api_key=key, api_base=base),
        summary_llm,
    )


def build_query_engine(
    docs_path: str | Path,
    *,
    embed_model: Any = None,
    llm: Any = None,
    show_progress: bool = False,
    top_k: int = 3,
) -> Any:
    from llama_index.core import Document, VectorStoreIndex
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.query_engine import RetrieverQueryEngine
    from llama_index.core.retrievers import QueryFusionRetriever

    from .retrieval import LexicalRetriever

    root = Path(docs_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError("Configured knowledge directory does not exist")
    documents = [
        Document(text=p.read_text(encoding="utf-8"), metadata={"file_name": p.name})
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix in {".txt", ".md"}
    ]
    if not documents or not any(d.text.strip() for d in documents):
        raise ValueError("No non-empty UTF-8 .md/.txt documents")
    if embed_model is None or llm is None:
        default_embed, default_llm = configured_models()
        embed_model = embed_model or default_embed
        llm = llm or default_llm
    nodes = SentenceSplitter(chunk_size=512, chunk_overlap=32).get_nodes_from_documents(documents)
    index = VectorStoreIndex(nodes, embed_model=embed_model, show_progress=show_progress)
    fused = QueryFusionRetriever(
        [index.as_retriever(similarity_top_k=top_k), LexicalRetriever(nodes, top_k=top_k)],
        llm=llm,
        num_queries=1,
        similarity_top_k=top_k,
        mode="reciprocal_rerank",
        use_async=True,
    )
    # 檢索工具只回傳來源摘錄，由已選定的 Agent 模型回答，避免第二次模型路由。
    from llama_index.core.response_synthesizers.no_text import NoText

    return RetrieverQueryEngine(fused, response_synthesizer=NoText(llm=llm))


async def abuild_query_engine(docs_path: str | Path, **kwargs: Any) -> Any:
    # Initialize native dependencies on the event-loop thread before dispatching
    # index work. First importing NumPy in a Windows MCP worker can stall DLL loading.
    from llama_index.core import VectorStoreIndex  # noqa: F401

    return await asyncio.to_thread(build_query_engine, docs_path, **kwargs)


def format_response(response: Any) -> str:
    if not hasattr(response, "source_nodes"):
        return str(response)
    sources = [
        {
            "file": n.node.metadata.get("file_name", "unknown"),
            "text": n.node.get_content(),
            "score": n.score,
        }
        for n in response.source_nodes
    ]
    answer = response.response or "\n\n".join(s["text"] for s in sources)
    return json.dumps({"answer": answer, "sources": sources}, ensure_ascii=False)


async def _aquery(engine: Any, query: str) -> str:
    if not query.strip():
        raise ValueError("query must not be blank")
    return format_response(await engine.aquery(query))


def as_langchain_tool(engine: Any) -> Any:
    from langchain_core.tools import StructuredTool

    def run(query: str) -> str:
        return format_response(engine.query(query))

    async def arun(query: str) -> str:
        return await _aquery(engine, query)

    return StructuredTool.from_function(
        func=run,
        coroutine=arun,
        name=_TOOL_NAME,
        description=_TOOL_DESCRIPTION,
    )


def as_mcp_tool_spec(*, engine_factory: Callable[..., Any] = abuild_query_engine) -> dict[str, Any]:
    # Each server owns its index. Knowledge paths are configured by the operator.
    engine: Any = None
    lock = asyncio.Lock()

    async def retrieve(query: str) -> str:
        nonlocal engine
        if not query.strip():
            raise ValueError("query must not be blank")
        async with lock:
            if engine is None:
                path = os.getenv(DEFAULT_DOCS_PATH_ENV) or str(DEFAULT_DOCS_PATH)
                engine = await engine_factory(path)
        return await _aquery(engine, query)

    return {"name": _TOOL_NAME, "description": _TOOL_DESCRIPTION, "func": retrieve}
