"""LoRA SFT on reviewed teacher examples; Linux/CUDA required for --train."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edge_reasoner.core import parse_response, read_jsonl  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/sft_dataset.jsonl")
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--output", type=Path, default=ROOT / "models/sft_model_7b")
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    rows = read_jsonl(args.dataset)
    if not rows:
        raise SystemExit("No SFT rows. Run phase 1 with API access and review examples.")
    for row in rows:
        if not row.get("reviewed") or not parse_response(row.get("response", "")):
            raise SystemExit(f"Unreviewed or invalid example: {row.get('id')}")
    print(f"Validated {len(rows)} reviewed SFT examples; base={args.base_model}")
    if not args.train:
        return
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required")
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastLanguageModel, is_bfloat16_supported

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=2048,
        load_in_4bit=True,
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
    texts = [
        tokenizer.apply_chat_template(
            [
                {"role": "user", "content": row["prompt"]},
                {"role": "assistant", "content": row["response"]},
            ],
            tokenize=False,
            add_generation_prompt=False,
        )
        for row in rows
    ]
    dataset = Dataset.from_dict({"text": texts})
    config = SFTConfig(
        output_dir=str(args.output) + "_checkpoints",
        max_steps=args.max_steps,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        optim="adamw_8bit",
        max_seq_length=2048,
        dataset_text_field="text",
        bf16=is_bfloat16_supported(),
        fp16=not is_bfloat16_supported(),
        logging_steps=5,
        report_to="none",
        seed=3407,
    )
    trainer = SFTTrainer(
        model=model, processing_class=tokenizer, train_dataset=dataset, args=config
    )
    trainer.train()
    adapter = Path(str(args.output) + "_lora")
    model.save_pretrained(str(adapter))
    tokenizer.save_pretrained(str(adapter))
    model.save_pretrained_merged(str(args.output), tokenizer, save_method="merged_16bit")
    print(f"Saved LoRA and merged model: {adapter}, {args.output}")


if __name__ == "__main__":
    main()
