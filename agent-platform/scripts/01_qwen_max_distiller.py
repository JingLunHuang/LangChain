"""Prepare GRPO prompts and optionally distill grounded SFT examples."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edge_reasoner.core import load_seeds, parse_response, read_jsonl, write_jsonl  # noqa: E402
from edge_reasoner.qwen import QwenClient  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute", action="store_true", help="Call Qwen-Max for grounded basic seeds"
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    seeds = load_seeds(ROOT / "data/seed_questions.json")
    basic = [row for row in seeds if row["split"] == "basic"]
    explore = [row for row in seeds if row["split"] == "explore"]
    write_jsonl(
        ROOT / "data/grpo_prompts.jsonl",
        [
            {"id": row["id"], "prompt": row["question"], "source": "human_seed", "split": "train"}
            for row in explore
        ],
    )
    print(f"Prepared {len(explore)} GRPO prompts; {len(basic)} grounded basic seeds available")
    if not args.execute:
        return
    if args.limit < 1:
        raise ValueError("--limit must be positive")
    client = QwenClient()
    preference = (ROOT / "data/preference.md").read_text(encoding="utf-8")
    output = ROOT / "data/sft_dataset.jsonl"
    rejected = ROOT / "data/rejected.jsonl"
    rows = read_jsonl(output)
    failures = read_jsonl(rejected)
    existing = {row["id"] for row in rows}
    for seed in basic[: args.limit]:
        if seed["id"] in existing:
            continue
        user = f"問題：{seed['question']}\n已核對事實：{seed['facts']}\n\n示範偏好：\n{preference}"
        system = (
            "根據已核對事實回答。只能輸出 <thinking>簡短、可核對的判斷依據</thinking>"
            "<answer>繁體中文結論</answer>。thinking 是供使用者閱讀的依據摘要，不是隱藏思維鏈。"
            "不能捏造保單條款、事故或圖片細節。"
        )
        try:
            answer = client.chat(system, user)
            if not parse_response(answer):
                raise ValueError("teacher response failed XML validation")
            row = {
                "id": seed["id"],
                "prompt": seed["question"],
                "response": answer,
                "facts": seed["facts"],
                "source": "qwen_max_unreviewed",
                "reviewed": False,
            }
            rows.append(row)
            existing.add(seed["id"])
            write_jsonl(output, rows)
        except (RuntimeError, ValueError) as exc:
            failures.append({"id": seed["id"], "reason": str(exc)})
            write_jsonl(rejected, failures)
            print(f"Rejected {seed['id']}: {exc}")
            if "HTTP 429" in str(exc):
                print("Rate limit reached; stopping to avoid repeated API calls")
                break
    print(f"SFT rows={len(rows)}; API calls={client.calls}; human review required before training")


if __name__ == "__main__":
    main()
