"""Repeatable, evidence-preserving loopback backtest of the integrated Edge Agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edge_reasoner.core import (  # noqa: E402
    parse_response,
    preference_penalty,
    read_jsonl,
    write_jsonl,
)


def json_file(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases() -> tuple[list[dict], dict]:
    holdout_path = ROOT / "data/eval_cases.json"
    seed_path = ROOT / "data/seed_questions.json"
    cases = json_file(holdout_path)
    seeds = json_file(seed_path)
    if not isinstance(cases, list) or not isinstance(seeds, list) or not cases:
        raise ValueError("Holdout and seeds must be non-empty lists")
    case_ids = [row["id"] for row in cases]
    seed_ids = [row["id"] for row in seeds]
    if len(case_ids) != len(set(case_ids)) or len(seed_ids) != len(set(seed_ids)):
        raise ValueError("Duplicate case or seed ID")
    if set(case_ids) & set(seed_ids):
        raise ValueError("Holdout IDs overlap seed IDs")

    def normalized(value):
        return "".join(str(value).lower().split())

    if {normalized(row["question"]) for row in cases} & {
        normalized(row["question"]) for row in seeds
    }:
        raise ValueError("Exact holdout question overlaps seed questions")
    return cases, {
        "holdout_sha256": digest(holdout_path),
        "seed_sha256": digest(seed_path),
        "exact_question_overlap": False,
    }


def request(url: str, key: str | None = None, payload: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    headers = {"Content-Type": "application/json"} if body else {}
    if key:
        headers["X-API-Key"] = key
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=240) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc)
        except (ValueError, OSError):
            detail = {"detail": "HTTP error"}
        return exc.code, detail


def run_live(base: str, key: str, cases: list[dict], repeats: int) -> tuple[dict, list[dict]]:
    health_code, health = request(base + "/health")
    preview_code, preview = request(base + "/demo/models")
    unauthorized, _ = request(base + "/v1/edge/status")
    status_code, status = request(base + "/v1/edge/status", key)
    checks = {
        "health": health_code == 200 and health.get("status") == "ok",
        "original_preview": preview_code == 200 and isinstance(preview, list) and bool(preview),
        "edge_auth": unauthorized == 401,
        "edge_status": status_code == 200,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Platform preflight failed: {checks}")
    rows: list[dict] = []
    for case in cases:
        for repeat in range(1, repeats + 1):
            started = time.perf_counter()
            try:
                code, result = request(
                    base + "/v1/edge/run",
                    key,
                    {"question": case["question"], "allow_cloud_fallback": False},
                )
                error = None if code == 200 else result.get("detail", "HTTP error")
            except (OSError, ValueError) as exc:
                code, result, error = 0, {}, type(exc).__name__
            rows.append(
                {
                    "case_id": case["id"],
                    "repeat": repeat,
                    "http_status": code,
                    "latency_seconds": round(time.perf_counter() - started, 3),
                    "route": result.get("route"),
                    "response": result.get("response"),
                    "reason_summary": result.get("reason_summary"),
                    "answer": result.get("answer"),
                    "perception": result.get("perception"),
                    "sources": result.get("sources"),
                    "local_calls": result.get("local_calls"),
                    "cloud_calls": result.get("cloud_calls"),
                    "error": error,
                }
            )
            print(
                f"{case['id']} repeat={repeat} http={code} route={rows[-1]['route']} ",
                f"latency={rows[-1]['latency_seconds']}s",
                flush=True,
            )
    return {
        "checks": checks,
        "deployment": status.get("deployment", {}),
        "model_files": status.get("models", {}),
    }, rows


def summarize(
    cases: list[dict],
    rows: list[dict],
    preflight: dict,
    integrity: dict,
    reviews: dict,
    repeats: int,
) -> dict:
    expected = {(case["id"], repeat) for case in cases for repeat in range(1, repeats + 1)}
    actual = [(row["case_id"], row["repeat"]) for row in rows]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise ValueError("Response rows must exactly cover every holdout case and repeat")
    details = []
    for row in rows:
        pair = parse_response(row.get("response") or "")
        review_key = f"{row['case_id']}#{row['repeat']}"
        review = reviews.get(review_key)
        if review is not None and (
            not isinstance(review, dict)
            or type(review.get("pass")) is not bool
            or not isinstance(review.get("note"), str)
            or not review["note"].strip()
        ):
            raise ValueError(f"Invalid human review for {review_key}")
        auto = {
            "http_ok": row["http_status"] == 200,
            "xml_format": pair is not None,
            "lexical_safety": preference_penalty(row.get("response") or "") == 0,
            "cloud_not_used": row.get("cloud_calls") == 0,
            "local_used": isinstance(row.get("local_calls"), int) and row["local_calls"] >= 1,
        }
        details.append(
            {
                "case_id": row["case_id"],
                "repeat": row["repeat"],
                "auto_checks": auto,
                "auto_pass": all(auto.values()),
                "human_review": review,
                "latency_seconds": row["latency_seconds"],
                "route": row["route"],
            }
        )
    latencies = [row["latency_seconds"] for row in rows]
    auto_pass = sum(item["auto_pass"] for item in details)
    reviewed = sum(item["human_review"] is not None for item in details)
    factual_pass = sum(
        item["human_review"] is not None and item["human_review"]["pass"] for item in details
    )
    if auto_pass != len(details) or (reviewed and factual_pass != reviewed):
        overall = "failed"
    elif reviewed != len(details):
        overall = "needs_human_review"
    else:
        overall = "passed_small_sample"
    return {
        "schema_version": 1,
        "kind": "observed_agent_backtest",
        "overall": overall,
        "holdout": integrity,
        "preflight": preflight,
        "n_cases": len(cases),
        "repeats": repeats,
        "n_runs": len(details),
        "auto_pass_runs": auto_pass,
        "human_reviewed_runs": reviewed,
        "human_pass_runs": factual_pass,
        "latency_seconds": {
            "mean": round(statistics.mean(latencies), 3),
            "median": round(statistics.median(latencies), 3),
            "min": min(latencies),
            "max": max(latencies),
        },
        "model_matrix": {
            "base_local": preflight.get("deployment", {}).get("text_model"),
            "sft_weights_present": preflight.get("model_files", {}).get("sft"),
            "co_work_weights_present": preflight.get("model_files", {}).get("final"),
        },
        "judge_score": None,
        "tokens_per_second": None,
        "cost_savings": None,
        "limits": [
            "Three holdout cases are a pipeline check, not statistical evidence.",
            "No teacher judge or three-model comparison without observed weights and API calls.",
            "Human review checks factual grounding; XML and lexical checks alone do not.",
        ],
        "per_run": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--key-file", type=Path, default=ROOT / ".state/demo-key.json")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument(
        "--replay", action="store_true", help="Re-score saved responses without model calls"
    )
    parser.add_argument(
        "--review-file", type=Path, help="JSON mapping case_id#repeat to {pass: bool, note: str}"
    )
    parser.add_argument("--responses", type=Path, default=ROOT / "outputs/backtest_responses.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/backtest.json")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        raise ValueError("--repeats must be 1..5")
    parsed = urlparse(args.url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Backtest URL must be a local HTTP service")
    cases, integrity = load_cases()
    if args.replay:
        rows = read_jsonl(args.responses)
        old = json_file(args.output)
        preflight = old["preflight"]
        if old["holdout"] != integrity:
            raise ValueError("Saved responses use different holdout or seeds")
    else:
        key = json_file(args.key_file)["api_key"]
        preflight, rows = run_live(args.url.rstrip("/"), key, cases, args.repeats)
        write_jsonl(args.responses, rows)
    reviews = json_file(args.review_file) if args.review_file else {}
    if not isinstance(reviews, dict):
        raise ValueError("Review file must contain an object")
    report = summarize(cases, rows, preflight, integrity, reviews, args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "overall",
                    "n_runs",
                    "auto_pass_runs",
                    "human_reviewed_runs",
                    "human_pass_runs",
                    "latency_seconds",
                    "model_matrix",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"Wrote {args.responses} and {args.output}")


if __name__ == "__main__":
    main()
