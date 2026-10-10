"""Export an actually trained merged text model to two Ollama-ready GGUFs."""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=Path("models/final_co_work_model_7b"))
    parser.add_argument("--output", type=Path, default=Path("agent"))
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    if not args.model.is_dir():
        raise SystemExit(f"Trained model missing: {args.model}")
    if not args.export:
        print(f"Ready to export {args.model} to {args.output} with Q4_K_M and Q8_0")
        return
    import torch

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required for this Unsloth export path")
    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        str(args.model), max_seq_length=4096, load_in_4bit=False
    )
    args.output.mkdir(parents=True, exist_ok=True)
    for quantization in ("q4_k_m", "q8_0"):
        destination = args.output / f"model-{quantization}"
        model.save_pretrained_gguf(str(destination), tokenizer, quantization_method=quantization)
        print(f"Exported {quantization} into {destination}")
    q4_files = list((args.output / "model-q4_k_m").rglob("*.gguf"))
    if len(q4_files) != 1:
        raise RuntimeError(f"Expected one Q4_K_M GGUF, found {len(q4_files)}")
    relative = q4_files[0].relative_to(args.output).as_posix()
    modelfile = args.output / "Modelfile"
    modelfile.write_text(
        f"FROM ./{relative}\nPARAMETER temperature 0.2\nPARAMETER num_ctx 4096\n"
        'SYSTEM "請用繁體中文回答。僅依已知證據，輸出 <thinking>簡短可核對依據</thinking>'
        '<answer>結論</answer>。資料不足時說明缺口；不得捏造保單或事故資訊。"\n',
        encoding="utf-8",
    )
    print(f"Wrote {modelfile}; ollama create edge-reasoner -f {modelfile}")


if __name__ == "__main__":
    main()
