"""Dependency-free validation shared by distillation, training, and evaluation."""

from __future__ import annotations

import json
import re
from pathlib import Path

XML = re.compile(r"\A\s*<thinking>(.*?)</thinking>\s*<answer>(.*?)</answer>\s*\Z", re.S)
UNSUPPORTED = ("保證理賠", "一定理賠", "保證承保", "一定承保", "無條件賠付")


def parse_response(value: str) -> tuple[str, str] | None:
    match = XML.fullmatch(value)
    if not match:
        return None
    thinking, answer = (part.strip() for part in match.groups())
    if not thinking or not answer or "<" in thinking or "<" in answer:
        return None
    return thinking, answer


def hard_rule_score(value: str) -> float:
    return float(parse_response(value) is not None)


def preference_penalty(value: str) -> float:
    """Transparent lexical guard; a reviewer must still inspect factual quality."""
    return 1.0 if any(term in value for term in UNSUPPORTED) else 0.0


def combined_reward(response: str, judge_score: float) -> float:
    if not 0 <= judge_score <= 1:
        raise ValueError("judge_score must be in [0, 1]")
    if not parse_response(response):
        return -1.0
    return 0.3 + 0.7 * judge_score - preference_penalty(response)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected object")
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    temporary.replace(path)


def load_seeds(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    ids = set()
    for row in rows:
        if (
            row.get("split") not in {"basic", "explore"}
            or not row.get("id")
            or not row.get("question")
        ):
            raise ValueError(f"Invalid seed: {row!r}")
        if row["id"] in ids:
            raise ValueError(f"Duplicate seed id: {row['id']}")
        ids.add(row["id"])
    return rows
