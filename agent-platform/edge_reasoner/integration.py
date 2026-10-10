"""UI-neutral facade for embedding Edge Reasoner into an existing platform."""

from __future__ import annotations

import json
import os
from pathlib import Path

from edge_reasoner.core import load_seeds, parse_response, read_jsonl
from edge_reasoner.orchestrator import build_graph

DEFAULT_ROOT = Path(__file__).resolve().parents[1]


class EdgeFacade:
    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = root.resolve()

    @property
    def data_dir(self) -> Path:
        source_data = self.root / "data"
        return source_data if source_data.is_dir() else Path(__file__).with_name("data")

    def status(self) -> dict:
        data = self.data_dir
        seeds = load_seeds(data / "seed_questions.json")
        sft = read_jsonl(data / "sft_dataset.jsonl")
        prompts = read_jsonl(data / "grpo_prompts.jsonl")
        rollouts = read_jsonl(data / "rollouts.jsonl")
        report_path = self.root / "outputs/evaluation.json"
        report = (
            json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
        )
        backtest = self.backtest()
        return {
            "backtest_available": backtest is not None,
            "backtest_overall": backtest.get("overall") if backtest else None,
            "deployment": {
                "text_model": os.environ.get("OLLAMA_TEXT_MODEL", "edge-reasoner"),
                "vision_model": os.environ.get("OLLAMA_VISION_MODEL") or None,
            },
            "seed_questions": len(seeds),
            "sft_examples": len(sft),
            "reviewed_sft_examples": sum(row.get("reviewed") is True for row in sft),
            "grpo_prompts": len(prompts),
            "observed_rollouts": len(rollouts),
            "models": {
                "sft": (self.root / "models/sft_model_7b").is_dir(),
                "grpo": (self.root / "models/grpo_model_7b").is_dir(),
                "final": (self.root / "models/final_co_work_model_7b").is_dir(),
            },
            "evaluation_available": report is not None,
            "evaluated_models": sorted(report.get("models", {})) if report else [],
            "teacher_key_configured": bool(os.environ.get("DASHSCOPE_API_KEY")),
            "training_environment": (
                "Check CUDA on the training host; status does not assume availability"
            ),
        }

    def backtest(self) -> dict | None:
        path = self.root / "outputs/backtest.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def evaluation(self) -> dict | None:
        path = self.root / "outputs/evaluation.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def run(
        self,
        question: str,
        *,
        image: bytes | None = None,
        allow_cloud_fallback: bool = False,
        text_model: str | None = None,
        vision_model: str | None = None,
    ) -> dict:
        if not question.strip() or len(question) > 16000:
            raise ValueError("Question must contain 1–16000 characters")
        if image is not None and len(image) > 10 * 1024 * 1024:
            raise ValueError("Image exceeds 10 MB")
        if allow_cloud_fallback and not os.environ.get("DASHSCOPE_API_KEY"):
            raise ValueError("DASHSCOPE_API_KEY is not configured")
        graph = build_graph(
            text_model=text_model or os.environ.get("OLLAMA_TEXT_MODEL", "edge-reasoner"),
            vision_model=vision_model or os.environ.get("OLLAMA_VISION_MODEL") or None,
            knowledge_dir=self.data_dir / "knowledge",
            allow_cloud_fallback=allow_cloud_fallback,
        )
        result = graph.invoke(
            {"question": question, "image": image, "local_calls": 0, "cloud_calls": 0}
        )
        parts = parse_response(result["response"])
        return {
            "route": result["route"],
            "response": result["response"],
            "reason_summary": parts[0] if parts else None,
            "answer": parts[1] if parts else None,
            "perception": result.get("perception", {}),
            "sources": [
                source.split("]", 1)[0].removeprefix("[") for source in result.get("sources", [])
            ],
            "local_calls": result.get("local_calls", 0),
            "cloud_calls": result.get("cloud_calls", 0),
        }
