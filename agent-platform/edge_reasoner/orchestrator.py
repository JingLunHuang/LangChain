"""LangGraph: perception, local retrieval, local reasoning, optional Qwen fallback."""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from edge_reasoner.core import parse_response, preference_penalty
from edge_reasoner.qwen import QwenClient

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KNOWLEDGE = (
    ROOT / "data/knowledge"
    if (ROOT / "data/knowledge").is_dir()
    else Path(__file__).with_name("data") / "knowledge"
)


class AgentState(TypedDict, total=False):
    question: str
    image: bytes | None
    perception: dict
    sources: list[str]
    response: str
    route: str
    local_calls: int
    cloud_calls: int


def ollama_chat(
    model: str, content: str, *, image: bytes | None = None, json_mode: bool = False
) -> str:
    message: dict = {"role": "user", "content": content}
    if image is not None:
        message["images"] = [base64.b64encode(image).decode("ascii")]
    payload: dict = {"model": model, "messages": [message], "stream": False, "think": False}
    if json_mode:
        payload["format"] = "json"
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    request = urllib.request.Request(
        base + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)["message"]["content"]


def ollama_chat_stream(model: str, content: str):
    """Yield visible answer chunks from Ollama's newline-delimited JSON stream."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": True,
        "think": False,
    }
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    request = urllib.request.Request(
        base + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        for line in response:
            if line.strip():
                item = json.loads(line)
                chunk = item.get("message", {}).get("content", "")
                if chunk:
                    yield chunk


def retrieve(question: str, perception: dict, knowledge_dir: Path, limit: int = 3) -> list[str]:
    if not knowledge_dir.is_dir():
        return []
    query = question + json.dumps(perception, ensure_ascii=False)
    grams = {query[index : index + 2] for index in range(len(query) - 1)}
    ranked = []
    for path in knowledge_dir.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        score = sum(gram in content for gram in grams)
        if score:
            ranked.append((score, path.name, content[:3000]))
    ranked.sort(reverse=True)
    return [f"[{name}] {content}" for _, name, content in ranked[:limit]]


def build_graph(
    *,
    text_model: str,
    vision_model: str | None = None,
    knowledge_dir: Path = DEFAULT_KNOWLEDGE,
    allow_cloud_fallback: bool = False,
    generate: Callable[[str, str], str] = ollama_chat,
):
    from langgraph.graph import END, START, StateGraph

    def perception_node(state: AgentState) -> dict:
        if not state.get("image"):
            return {"perception": {}}
        if not vision_model:
            return {"perception": {"status": "vision_model_not_configured"}}
        raw = ollama_chat(
            vision_model,
            "讀取可見的儀表或車損資訊。只輸出 JSON；不確定值用 null，勿判定理賠。",
            image=state["image"],
            json_mode=True,
        )
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("expected object")
        except (ValueError, TypeError):
            value = {"status": "vision_output_invalid", "raw_excerpt": raw[:200]}
        return {"perception": value, "local_calls": state.get("local_calls", 0) + 1}

    def retrieval_node(state: AgentState) -> dict:
        return {"sources": retrieve(state["question"], state.get("perception", {}), knowledge_dir)}

    def reasoning_node(state: AgentState) -> dict:
        perception_status = state.get("perception", {}).get("status")
        if state.get("image") and perception_status:
            return {
                "response": (
                    "<thinking>圖片未經有效的視覺模型解析，沒有可核對的圖片資訊。</thinking>"
                    "<answer>目前無法判讀這張圖片。請設定視覺模型或提供可核對的文字資訊；"
                    "不能僅憑未解析的圖片作理賠結論。</answer>"
                ),
                "local_calls": state.get("local_calls", 0),
            }
        context = json.dumps(
            {
                "question": state["question"],
                "perception": state.get("perception", {}),
                "retrieved_text": state.get("sources", []),
            },
            ensure_ascii=False,
        )
        instruction = (
            "請用繁體中文回答。僅根據提供的資料，用 <thinking>簡短可核對依據</thinking>"
            "<answer>結論</answer>；無正式保單不得斷言理賠結果。thinking 是公開依據摘要。\n"
            + context
        )
        answer = generate(text_model, instruction)
        return {"response": answer, "local_calls": state.get("local_calls", 0) + 1}

    def route_after_reasoning(state: AgentState) -> str:
        if state.get("image") and state.get("perception", {}).get("status"):
            return "finish"
        invalid = not parse_response(state["response"]) or preference_penalty(state["response"]) > 0
        return "fallback" if invalid and allow_cloud_fallback else "finish"

    def fallback_node(state: AgentState) -> dict:
        client = QwenClient()
        context = json.dumps(
            {
                "question": state["question"],
                "perception": state.get("perception", {}),
                "sources": state.get("sources", []),
            },
            ensure_ascii=False,
        )
        result = client.chat(
            (
                "請輸出 <thinking>簡短可核對依據</thinking><answer>繁體中文結論</answer>；"
                "不捏造缺少的條款、圖片細節。"
            ),
            context,
        )
        route = (
            "cloud_fallback"
            if parse_response(result) and not preference_penalty(result)
            else "needs_review"
        )
        return {
            "response": result,
            "route": route,
            "cloud_calls": state.get("cloud_calls", 0) + client.calls,
        }

    def finish_node(state: AgentState) -> dict:
        passed = (
            parse_response(state["response"])
            and not preference_penalty(state["response"])
            and not (state.get("image") and state.get("perception", {}).get("status"))
        )
        return {"route": "local" if passed else "needs_review"}

    graph = StateGraph(AgentState)
    graph.add_node("perception", perception_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("reasoning", reasoning_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("finish", finish_node)
    graph.add_edge(START, "perception")
    graph.add_edge("perception", "retrieval")
    graph.add_edge("retrieval", "reasoning")
    graph.add_conditional_edges(
        "reasoning", route_after_reasoning, {"fallback": "fallback", "finish": "finish"}
    )
    graph.add_edge("fallback", END)
    graph.add_edge("finish", END)
    return graph.compile()
