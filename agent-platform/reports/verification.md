# 本機驗收紀錄

日期：2026-09-28。環境：Windows、CPython 3.12.14、uv 0.12.5；鎖檔包含 139 個套件。以下是本機觀察，不等同所有 CI 矩陣或真實模型供應商已驗證。

| 檢查 | 結果 | 證據 |
| --- | --- | --- |
| 依賴安裝與鎖定 | 完成 | pyproject.toml 與 uv.lock |
| Ruff check | 通過 | `ruff check .` 回報 All checks passed |
| Ruff format | 通過 | `ruff format --check .` 通過 |
| 完整測試（繁體化後） | 35 passed，0 failed，6 warnings | reports/junit.xml；10.05 秒 |
| MCP 傳輸 | stdio、SSE、Streamable HTTP 通過 | 真正 ClientSession 握手、list_tools、call_tool、resource、prompt、agent_invoke |
| 網路診斷範例 MCP | 通過 | 四個模擬工具可列出，ping_tool 的日誌不破壞 stdout 協議 |
| 真實 HTTP 冒煙 | 通過 | [http-smoke.json](http-smoke.json)：auth、hybrid retrieval、session follow-up、97 deltas、DONE |
| 上下文預算量測 | 完成 | [context-benchmark.json](context-benchmark.json)：29,572 → 1,198，預算 1,200 |
| 註解繁體化 | 完成 | [annotation-localization.json](annotation-localization.json)：35 檔、8 檔變更、20 處註解／docstring，可執行 AST 不變 |
| 離線套件建置 | source distribution 與 wheel 成功 | dist/；使用本機已快取的 build dependency |
| 包裝內容 | 知識庫已包含，敏感與快取路徑排除 | wheel 包含三個 examples/knowledge 文件；未包含 .state、.venv、.uv-cache、__pycache__ |
| 發行包獨立載入 | 通過 | [packaging-check.json](packaging-check.json)；從解開的 wheel 匯入、保留 stdlib platform，並執行混合檢索 |

供應商 API 與 GPU 推理後端尚未測試。離線 DemoEmbedding 是詞彙雜湊向量，DemoChatModel 是確定性測試模型；它們用於證明整合行為，不能用來宣稱語義檢索品質或生成品質。

目前六個 warning 是套件的棄用提醒：langchain-community、舊版 Streamable HTTP convenience wrapper，以及保留的教學記憶範例。沒有測試失敗；API 正式路徑使用獨立 AgentRuntime。

先前需要連網的 build 工具呼叫因自動核准服務使用量限制未執行；後續 `uv build --offline` 已使用本機快取成功建置。繁體化後再次執行完整測試通過。
