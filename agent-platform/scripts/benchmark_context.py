"""Measure application context size; does not claim GPU KV hit rate or TTFT."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from core.cache_optimizer.optimizer import ContextOptimizer, estimate_tokens

ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    optimizer = ContextOptimizer("固定 system prefix", max_tokens=1200)
    history = [
        {"role": role, "content": f"turn {i}: " + "中文資料 facts " * 25}
        for i in range(30)
        for role in ["user", "assistant"]
    ]
    history.append({"role": "user", "content": "請保留最新問題與訂單 98765"})
    before = optimizer.build_prefix() + history
    after = await optimizer.optimize(history)
    result = {
        "measurement": "UTF-8 input byte bound with estimated framing",
        "input_before": estimate_tokens(before),
        "input_after": estimate_tokens(after),
        "budget": optimizer.max_tokens,
        "latest_request_preserved": after[-1] == history[-1],
        "prefix_preserved": after[:1] == optimizer.build_prefix(),
        "gpu_kv_hit_rate": None,
        "ttft_ms": None,
        "tokens_per_second": None,
    }
    path = ROOT / "reports" / "context-benchmark.json"
    await asyncio.to_thread(path.parent.mkdir, exist_ok=True)
    await asyncio.to_thread(path.write_text, json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
