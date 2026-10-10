"""Evaluate actual saved responses; run the agent with the separate app entry point."""

import argparse
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edge_reasoner.core import (  # noqa: E402
    hard_rule_score,
    preference_penalty,
    read_jsonl,
    write_jsonl,
)
from edge_reasoner.qwen import QwenClient  # noqa: E402


def ollama_response(model: str, question: str) -> tuple[str, int, float]:
    """Run an installed Ollama model and retain observed token and wall-time evidence."""
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "user",
                "content": (
                    "以繁體中文輸出 <thinking>簡短可核對依據</thinking>"
                    "<answer>結論</answer>。\n" + question
                ),
            }
        ],
    }
    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    request = urllib.request.Request(
        base + "/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=240) as response:
        result = json.load(response)
    elapsed = time.perf_counter() - started
    text = result["message"]["content"]
    tokens = result.get("eval_count")
    if not isinstance(tokens, int) or tokens < 1:
        raise ValueError("Ollama did not report output token count")
    return text, tokens, elapsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--responses",
        type=Path,
        default=ROOT / "outputs/eval_responses.jsonl",
        help="JSONL: case_id, model, response, output_tokens, latency_seconds",
    )
    parser.add_argument(
        "--generate", action="store_true", help="Run actual local models on the held-out cases"
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="name=model-path or name=ollama:installed-tag; repeat per model",
    )
    parser.add_argument(
        "--judge", action="store_true", help="Call Qwen-Max for each observed response"
    )
    parser.add_argument("--chart", action="store_true", help="Plot observed metrics only")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/evaluation.json")
    args = parser.parse_args()
    cases = {
        row["id"]: row
        for row in json.loads((ROOT / "data/eval_cases.json").read_text(encoding="utf-8"))
    }
    if args.generate:
        if not args.model:
            raise SystemExit("--generate requires at least one --model name=path")
        generated_rows = []
        for spec in args.model:
            name, separator, path = spec.partition("=")
            if not separator or not name or not path:
                raise ValueError("Expected --model name=path")
            if path.startswith("ollama:"):
                model_name = path.removeprefix("ollama:")
                if not model_name:
                    raise ValueError("Ollama model tag is required")
                for case in cases.values():
                    response, tokens, latency = ollama_response(model_name, case["question"])
                    generated_rows.append(
                        {
                            "case_id": case["id"],
                            "model": name,
                            "model_path": path,
                            "response": response,
                            "output_tokens": tokens,
                            "latency_seconds": latency,
                        }
                    )
                continue
            import torch

            if not torch.cuda.is_available():
                raise SystemExit("CUDA GPU required for Hugging Face model generation")
            from unsloth import FastLanguageModel

            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=path, max_seq_length=2048, load_in_4bit=True
            )
            FastLanguageModel.for_inference(model)
            for case in cases.values():
                prompt = tokenizer.apply_chat_template(
                    [
                        {
                            "role": "user",
                            "content": (
                                "以繁體中文輸出 <thinking>簡短可核對依據</thinking>"
                                "<answer>結論</answer>。\n"
                            )
                            + case["question"],
                        },
                    ],
                    tokenize=False,
                    add_generation_prompt=True,
                )
                inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
                torch.cuda.synchronize()
                started = time.perf_counter()
                with torch.no_grad():
                    output = model.generate(**inputs, max_new_tokens=384, do_sample=False)
                torch.cuda.synchronize()
                latency = time.perf_counter() - started
                tokens = output.shape[-1] - inputs["input_ids"].shape[-1]
                response = tokenizer.decode(output[0][-tokens:], skip_special_tokens=True)
                generated_rows.append(
                    {
                        "case_id": case["id"],
                        "model": name,
                        "model_path": path,
                        "response": response,
                        "output_tokens": tokens,
                        "latency_seconds": latency,
                    }
                )
            del model
            torch.cuda.empty_cache()
        write_jsonl(args.responses, generated_rows)
    rows = read_jsonl(args.responses)
    if not rows:
        raise SystemExit("No observed responses. This script does not fabricate model scores.")
    client = QwenClient() if args.judge else None
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        case = cases.get(row.get("case_id"))
        if case is None:
            raise ValueError(f"Unknown holdout case: {row.get('case_id')}")
        response = row["response"]
        latency = float(row["latency_seconds"])
        tokens = int(row["output_tokens"])
        if latency <= 0 or tokens < 0:
            raise ValueError("Invalid latency or token count")
        result = {
            "case_id": row["case_id"],
            "format": hard_rule_score(response),
            "preference_violation": preference_penalty(response),
            "tokens_per_second": tokens / latency,
        }
        if client:
            result["judge_score"] = client.judge(case["question"], response, case["facts"])
        grouped.setdefault(row["model"], []).append(result)
    summary = {}
    for name, values in grouped.items():
        case_ids = [item["case_id"] for item in values]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError(f"Duplicate case for model {name}")
        summary[name] = {
            key: statistics.mean(item[key] for item in values)
            for key in values[0]
            if key != "case_id"
        }
        summary[name]["n_cases"] = len(values)
    report = {
        "source": str(args.responses),
        "holdout": str(ROOT / "data/eval_cases.json"),
        "judge_model": client.model if client else None,
        "models": summary,
        "per_case": grouped,
        "model_sources": {row["model"]: row.get("model_path") for row in rows},
        "missing_comparison_models": sorted({"base", "sft", "co_work"} - set(summary)),
        "comparison_complete": {"base", "sft", "co_work"}.issubset(summary),
        "note": (
            "Teacher judge is subjective; no significance or cost-savings "
            "claim follows from this sample."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.chart:
        if len(summary) < 2 or any("judge_score" not in item for item in summary.values()):
            raise ValueError("Chart needs at least two observed models and --judge scores")
        import math

        import matplotlib.pyplot as plt
        import numpy as np

        labels = ["XML format", "Teacher score", "Speed (relative)"]
        angles = np.linspace(0, 2 * math.pi, len(labels), endpoint=False).tolist()
        max_speed = max(item["tokens_per_second"] for item in summary.values())
        fig, ax = plt.subplots(subplot_kw={"polar": True}, figsize=(6, 6))
        for name, item in summary.items():
            values = [item["format"], item["judge_score"], item["tokens_per_second"] / max_speed]
            ax.plot(angles + angles[:1], values + values[:1], label=name)
            ax.fill(angles + angles[:1], values + values[:1], alpha=0.08)
        ax.set_xticks(angles, labels)
        ax.set_ylim(0, 1)
        ax.legend(loc="upper right", bbox_to_anchor=(1.4, 1.1))
        chart = ROOT / "assets/eval_radar_chart.png"
        chart.parent.mkdir(exist_ok=True)
        fig.savefig(chart, bbox_inches="tight", dpi=160)
        plt.close(fig)
        print(f"Wrote observed chart: {chart}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
