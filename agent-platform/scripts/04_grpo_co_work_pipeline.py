"""GRPO with an explicit API judge budget, then reviewed RST selection."""

import argparse
import hashlib
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edge_reasoner.core import (  # noqa: E402
    combined_reward,
    parse_response,
    preference_penalty,
    read_jsonl,
    write_jsonl,
)
from edge_reasoner.qwen import QwenClient  # noqa: E402

SYSTEM = (
    "以繁體中文回答。嚴格輸出 <thinking>簡短、可核對的判斷依據</thinking>"
    "<answer>結論</answer>。不捏造圖片、事故、保單或法規資訊；資料不足時說明缺口。"
)


def select_rollouts(source: Path, output: Path, base: Path, fraction: float = 0.2) -> None:
    candidates = read_jsonl(source)
    if not candidates:
        raise SystemExit("No observed rollouts. Run the sample step after GRPO training.")
    eligible = []
    for row in candidates:
        response = row.get("response", "")
        judge_score = row.get("judge_score")
        recorded_reward = row.get("reward")
        if (
            not parse_response(response)
            or preference_penalty(response)
            or not isinstance(judge_score, (int, float))
            or not isinstance(recorded_reward, (int, float))
        ):
            continue
        if not 0 <= judge_score <= 1:
            continue
        verified_reward = combined_reward(response, judge_score)
        if abs(verified_reward - recorded_reward) < 1e-6 and verified_reward >= 0.7:
            eligible.append(row)
    eligible.sort(key=lambda row: row["reward"], reverse=True)
    count = math.ceil(len(candidates) * fraction)
    selected, seen = [], set()
    for row in eligible:
        if row["prompt_id"] not in seen:
            selected.append(
                {
                    "id": "rst-" + row["prompt_id"],
                    "prompt": row["prompt"],
                    "response": row["response"],
                    "source": "grpo_rst_unreviewed",
                    "reviewed": False,
                    "reward": row["reward"],
                }
            )
            seen.add(row["prompt_id"])
        if len(selected) >= count:
            break
    prior = read_jsonl(base)
    ids = {row["id"] for row in prior}
    combined = prior + [row for row in selected if row["id"] not in ids]
    write_jsonl(output, combined)
    print(
        f"Candidates={len(candidates)}, eligible={len(eligible)}, "
        f"selected={len(selected)}, round2={len(combined)}"
    )
    print("RST rows require human review before phase 2 round-two SFT")


def train(args: argparse.Namespace) -> None:
    prompts = read_jsonl(args.prompts)
    if not prompts:
        raise SystemExit("No GRPO prompts. Run phase 1 preparation first.")
    if args.judge_budget < args.generations:
        raise SystemExit("--judge-budget must cover at least one generation group")
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required")
    from datasets import Dataset
    from trl import GRPOConfig, GRPOTrainer
    from unsloth import FastLanguageModel, is_bfloat16_supported

    client = QwenClient()
    cache: dict[str, float] = {}
    prompt_by_text = {row["prompt"]: row for row in prompts}

    def reward_func(prompts, completions, **kwargs):
        scores = []
        for prompt, completion in zip(prompts, completions, strict=True):
            prompt_text = prompt if isinstance(prompt, str) else prompt[-1]["content"]
            response = completion if isinstance(completion, str) else completion[-1]["content"]
            question = prompt_text.split("\n\n", 1)[-1]
            if not parse_response(response):
                scores.append(-1.0)
                continue
            key = hashlib.sha256((question + "\0" + response).encode()).hexdigest()
            if key not in cache:
                if client.calls >= args.judge_budget:
                    raise RuntimeError(
                        "Qwen judge budget exhausted; checkpoint and resume with a new budget"
                    )
                facts = prompt_by_text.get(question, {}).get("facts", "")
                cache[key] = client.judge(question, response, facts)
            scores.append(combined_reward(response, cache[key]))
        return scores

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=2048,
        load_in_4bit=True,
        fast_inference=True,
        gpu_memory_utilization=0.6,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
    dataset = Dataset.from_dict({"prompt": [SYSTEM + "\n\n" + row["prompt"] for row in prompts]})
    config = GRPOConfig(
        output_dir=str(args.output) + "_checkpoints",
        max_steps=args.max_steps,
        per_device_train_batch_size=args.generations,
        gradient_accumulation_steps=1,
        num_generations=args.generations,
        max_prompt_length=512,
        max_completion_length=512,
        learning_rate=5e-6,
        optim="adamw_8bit",
        bf16=is_bfloat16_supported(),
        fp16=not is_bfloat16_supported(),
        logging_steps=1,
        report_to="none",
        seed=3407,
    )
    trainer = GRPOTrainer(
        model=model,
        processing_class=tokenizer,
        reward_funcs=reward_func,
        args=config,
        train_dataset=dataset,
    )
    trainer.train()
    adapter = Path(str(args.output) + "_lora")
    model.save_pretrained(str(adapter))
    tokenizer.save_pretrained(str(adapter))
    model.save_pretrained_merged(str(args.output), tokenizer, save_method="merged_16bit")
    print(f"Saved GRPO adapter and merged model; judge calls={client.calls}")


def sample(args: argparse.Namespace) -> None:
    """Generate fresh candidates from the trained model for RST inspection."""
    prompts = read_jsonl(args.prompts)
    if not prompts:
        raise SystemExit("No GRPO prompts")
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required")
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=2048,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    client = QwenClient()
    rows = read_jsonl(args.output)
    existing = {(row["prompt_id"], row["sample_index"]) for row in rows}
    for prompt in prompts:
        for index in range(args.samples_per_prompt):
            if (prompt["id"], index) in existing:
                continue
            if client.calls >= args.judge_budget:
                raise RuntimeError("Judge budget exhausted; existing candidates were saved")
            text = SYSTEM + "\n\n" + prompt["prompt"]
            inputs = tokenizer(text, return_tensors="pt").to(model.device)
            with torch.no_grad():
                generated = model.generate(
                    **inputs, max_new_tokens=512, do_sample=True, temperature=0.8, top_p=0.9
                )
            response = tokenizer.decode(
                generated[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
            )
            judge_score = (
                client.judge(prompt["prompt"], response) if parse_response(response) else 0.0
            )
            rows.append(
                {
                    "prompt_id": prompt["id"],
                    "prompt": prompt["prompt"],
                    "sample_index": index,
                    "response": response,
                    "judge_score": judge_score,
                    "reward": combined_reward(response, judge_score),
                }
            )
            write_jsonl(args.output, rows)
    print(f"Saved {len(rows)} observed candidates; judge calls={client.calls}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    training = sub.add_parser("train")
    training.add_argument("--prompts", type=Path, default=ROOT / "data/grpo_prompts.jsonl")
    training.add_argument("--base-model", default=str(ROOT / "models/sft_model_7b"))
    training.add_argument("--output", type=Path, default=ROOT / "models/grpo_model_7b")
    training.add_argument("--max-steps", type=int, default=30)
    training.add_argument("--generations", type=int, default=4)
    training.add_argument("--judge-budget", type=int, required=True)
    select = sub.add_parser("select")
    select.add_argument("--rollouts", type=Path, default=ROOT / "data/rollouts.jsonl")
    select.add_argument("--output", type=Path, default=ROOT / "data/sft_round2.jsonl")
    select.add_argument("--base", type=Path, default=ROOT / "data/sft_dataset.jsonl")
    sampling = sub.add_parser("sample")
    sampling.add_argument("--prompts", type=Path, default=ROOT / "data/grpo_prompts.jsonl")
    sampling.add_argument("--model", default=str(ROOT / "models/grpo_model_7b"))
    sampling.add_argument("--output", type=Path, default=ROOT / "data/rollouts.jsonl")
    sampling.add_argument("--samples-per-prompt", type=int, default=4)
    sampling.add_argument("--judge-budget", type=int, required=True)
    args = parser.parse_args()
    if args.command == "train":
        train(args)
    elif args.command == "sample":
        sample(args)
    else:
        select_rollouts(args.rollouts, args.output, args.base)


if __name__ == "__main__":
    main()
