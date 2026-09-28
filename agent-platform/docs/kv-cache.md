# KV-Cache Aware Application Design

KV Cache 的實際記憶體區塊與 PagedAttention 由推理引擎管理。平臺能控制送往模型的提示詞，讓相同前綴更容易重用，但不能直接操作顯存或保證快取命中。[vLLM Automatic Prefix Caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/)

## 穩定前綴

ContextOptimizer 接受明確設定的 system prompt 與 few-shot examples，將兩者作為固定前綴。若輸入已帶相同前綴，不再重複加入；不同的 system 訊息會被拒絕。API 不接受使用者輸入任意 system role。LangChain factory 不額外再加一份 system prompt，工具按名稱排序後綁定。

固定前綴不插入租戶、會話 ID、時間或變動摘要。摘要出現在前綴之後，以未信任的對話資料身份傳送。不同租戶的私有內容仍應由後端的隔離／快取策略保護，不能把快取命中當成存取權限。

## 輸入預算與歷史摘要

預設估算為 UTF-8 文字 byte 數加每條訊息 8 的 framing 估算，比中文四字元一 token 的假設更保守；它不是模型精確 tokenizer，也不涵蓋工具 schema、工具回傳或輸出 token。`ContextOptimizer(token_counter=...)` 可注入實際後端 tokenizer。操作者需保留工具與輸出空間。

超預算時保留最新 user 訊息與盡可能完整的最近輪次，將更早的歷史縮成摘要。指定 `summary_llm` 時由 LlamaIndex SummaryIndex 的 tree_summarize 執行；未指定時用含 `[omitted]` 的首尾摘錄。模型摘要與摘錄都可能遺失資訊，不承諾「無損」。API 的歷史儲存保留原始文字，摘要只修改單次請求副本；原始文字的保留期限仍受 64 輪、TTL 與容量限制。

若前綴加最新 user 訊息已超預算，拋出 ContextBudgetError，不截掉使用者的新問題。含 tool_calls 或 tool role 的進行中工具交換不接受此壓縮器，以免破壞呼叫與結果配對。

```python
from core.cache_optimizer.optimizer import ContextOptimizer
from core.data_engine.engine import configured_models

_, summary_llm = configured_models()  # 設定真實供應商後使用
optimizer = ContextOptimizer(
    system_prefix="Fixed instructions",
    max_tokens=4096,
    summary_llm=summary_llm,
)
messages = await optimizer.optimize(history + [{"role": "user", "content": question}])
```

在 API 自訂 Agent 可設定 `runtime.configs[agent_id]['summary_llm']`，注入相同 LlamaIndex LLM。預設離線示範不會為摘要發起模型呼叫。

## 串流

API 的 stream 與 invoke 共用 runtime.prepare。真實文字 delta 來自 LangChain graph 的 model message stream；工具事件不被誤當答案。串流 headers 包含 `Cache-Control: no-cache` 與 `X-Accel-Buffering: no`。需要壓縮時，摘要發生於第一個答案 token 前，因此會影響 TTFT；「不改變串流介面」不等於「沒有額外延遲」。

## 量測方法

`uv run python -m scripts.benchmark_context` 產生 `reports/context-benchmark.json`。目前只量測應用端文字輸入估算，範例為 29,572 → 1,198，固定前綴與最新問題保留。這不能解讀為 95% GPU 加速、實際 token 減少比例或快取命中率。

對後端進行比較時，固定模型、tokenizer、硬體、版本、工具 schema、輸出限制及並行度。用同一批請求比較未穩定前綴與穩定前綴，分別執行冷快取與暖快取；記錄 TTFT、總延遲、輸入／輸出 token、prefix cache 指標及摘要延遲。摘要是否保留決策與數值也需要評估，不只看文字長度。

| 後端指標 | 目前狀態 |
| --- | --- |
| KV / prefix cache hit rate | 待接推理引擎實測 |
| TTFT p50 / p95 | 待實測 |
| tokens/sec | 待實測 |
| 摘要資訊保留率 | 待建立評估資料 |

GPU PagedAttention adapter、語義答案快取與跨租戶快取共享不在現有功能範圍；目前交付的是可測試的應用端快取感知設計。
