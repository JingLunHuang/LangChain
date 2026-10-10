"""Validate corrected odometer labels and optionally fine-tune the vision model."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    parser.add_argument(
        "--allow-demo-two", action="store_true", help="Permit a two-image demonstration only"
    )
    parser.add_argument("--model", default="Qwen/Qwen2.5-VL-3B-Instruct")
    parser.add_argument("--output", type=Path, default=ROOT / "models/vl_3b_lora")
    args = parser.parse_args()
    labels = json.loads((ROOT / "data/vl_labels.json").read_text(encoding="utf-8"))
    for row in labels:
        image = (ROOT / row["image"]).resolve()
        if not image.is_relative_to(ROOT) or not image.is_file():
            raise SystemExit(f"Missing or unsafe image path: {row['image']}")
        label = row["label"]
        if label["speed_kmh"] < 0 or label["total_odometer"] < 0:
            raise SystemExit(f"Invalid numeric label: {row['id']}")
    print(f"Validated {len(labels)} corrected VL labels and image paths")
    if not args.train:
        return
    if len(labels) < 20 and not args.allow_demo_two:
        raise SystemExit(
            "Only two labelled images; use --allow-demo-two for a non-generalizable demonstration"
        )
    import torch
    from PIL import Image

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required")
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastVisionModel
    from unsloth.trainer import UnslothVisionDataCollator

    model, tokenizer = FastVisionModel.from_pretrained(
        args.model, use_gradient_checkpointing="unsloth"
    )
    model = FastVisionModel.get_peft_model(
        model,
        finetune_vision_layers=True,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        random_state=3407,
    )
    dataset = []
    for row in labels:
        dataset.append(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "讀取儀表資訊，只輸出可見欄位的 JSON；無法判讀填 null。",
                            },
                            {
                                "type": "image",
                                "image": Image.open(ROOT / row["image"]).convert("RGB"),
                            },
                        ],
                    },
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": json.dumps(row["label"], ensure_ascii=False)}
                        ],
                    },
                ]
            }
        )
    FastVisionModel.for_training(model)
    config = SFTConfig(
        output_dir=str(args.output) + "_checkpoints",
        per_device_train_batch_size=1,
        gradient_accumulation_steps=2,
        max_steps=30,
        learning_rate=2e-4,
        optim="adamw_8bit",
        report_to="none",
        remove_unused_columns=False,
        dataset_text_field="",
        dataset_kwargs={"skip_prepare_dataset": True},
    )
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        data_collator=UnslothVisionDataCollator(model, tokenizer),
        train_dataset=dataset,
        args=config,
    )
    trainer.train()
    model.save_pretrained(str(args.output))
    tokenizer.save_pretrained(str(args.output))
    print(f"Saved demonstration VL adapter: {args.output}")


if __name__ == "__main__":
    main()
