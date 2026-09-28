# 原始四階段規劃與全檔案稽核

日期：2026-09-28；本機 Windows / CPython 3.12.14。

**結論：核心 API、雙引擎檢索、原生 MCP 與串流確實可以執行，但尚不能認定所有檔案都嚴格完成原規劃。** 任務表把部分能力記為完成，需要區分固定配置與自動識別、可注入摘要與預設接通、測試通過與需求覆蓋。

本輪以檢查前的 **84 個交付檔案**為快照：59 個新平臺檔案、23 個課程/筆記/PDF/checkpoint 檔案、1 個父層 CI、1 個根目錄轉換腳本；另外檢查 2 個發行封裝及 dist/.gitignore。逐檔列出用途、規劃對應、檢查結果、問題編號、大小與 SHA-256；沒有用抽樣檔案代替全目錄盤點。

47 個 Python 檔全部 AST/compile 通過；8 份 notebook 的 14 個程式區塊可解析，未見已儲存 error output；64 頁 PDF 全部可擷取文字。TOML/lock、JSON/XML、CI YAML 與 PowerShell 啟動腳本皆完成結構檢查。**可解析不等於已重新執行原始付費模型案例**。

排除 .venv、.uv-cache、.state、__pycache__、工具/測試快取及 .test-tmp*：這些是依賴、私人狀態或執行產物，不屬交付原始碼。本輪新產生的 4 個稽核檔案另行檢查，不回算入 84 檔快照，避免報告自我引用。未讀取或輸出私人憑證。

完整資料：[逐檔 CSV](file-audit.csv)、[機器可讀 JSON](plan-audit.json)、[本輪 JUnit](plan-audit-junit.xml)。本輪只新增稽核輸出、重現既有量測及建立忽略範圍內的探測程式，沒有修正產品程式或改寫原始課程檔。

## 原規劃逐項對照

| 編號 | 階段 | 原始要求 | 判定 | 證據與限制 |
| --- | --- | --- | --- | --- |
| S1.1 | 一 | 閱讀三個主要程式、筆記與簡報 | 實作符合；來源路徑需修正 | 資產盤點涵蓋三個案例與 LCEL；本輪另讀其餘課程檔、8 份 notebook，64 頁 PDF 全部可擷取文字。F07 |
| S1.2 | 一 | 核心功能、優缺點與可重用模組分析 | 符合 | docs/asset-audit.md 明列工具鏈、模擬診斷、記憶、LCEL 與修復紀錄。 |
| S1.3 | 一 | 五層架構的 Mermaid 圖 | 符合 | docs/architecture.md 涵蓋接入、LangChain 編排、LlamaIndex 資料、MCP 協議及 ContextOptimizer 效能層。 |
| S1.4 | 一 | 具體 MCP 與 KV Cache 技術選型 | 符合應用層範圍 | 官方 MCP SDK/FastMCP、ContextOptimizer、可注入 tokenizer，以及 vLLM/SGLang 責任邊界已記錄；未實作 GPU PagedAttention。 |
| S2.1 | 二 | LlamaIndex QueryEngine 封裝為 MCP 或 LangChain Tool | 符合 | engine.py 的 as_langchain_tool/as_mcp_tool_spec；兩種入口均實際檢索並回傳來源，未使用 RetrievalQA。 |
| S2.2 | 二 | 原生 MCP Server，支援 stdio 與 SSE | 符合 | 原生 SDK；三種 transport 的握手與呼叫測試通過，另提供 Streamable HTTP。 |
| S2.3 | 二 | Resource/Prompt 擴充接口 | 符合 | register_resources/register_prompts，info://server 與 diagnose；列出、讀取及取得的協議測試通過。 |
| S2.4 | 二 | Poetry 或 uv 管理與依賴配置 | 符合 | 使用 uv；pyproject/uv.lock 可解析，uv lock --check --offline 通過，當前 Python 分支的已安裝版本符合鎖檔。 |
| S2.5 | 二 | 型別註解完整 | 部分完成 | 正式介面與範例仍有 4 處缺少參數或回傳型別；大量 Any，CI 沒有型別檢查。F08 |
| S2.6 | 二 | 非同步支援 | 符合 | Agent invoke/stream、MCP Client、摘要、QueryEngine.aquery 為非同步；建索引及 SQLite 透過執行緒處理。 |
| S2.7 | 二 | 完整目錄樹與核心整合類程式 | 符合 | README 目錄、core、mcp_server、platform_api、examples、tests、docs；platform_api 避免與標準函式庫名稱衝突。 |
| S2.8 | 二 | LangChain Router/Agent + LlamaIndex 獨立 Hybrid RAG | 符合整合要求 | VectorStoreIndex + BM25 + RRF；編排與資料引擎分層。離線雜湊向量只驗證整合，語義品質未量測。 |
| S2.9 | 二 | API Key 管理、多租戶及多 Agent 調度 | 符合單程序基礎 | Key 雜湊發行/列表/撤銷；tenant/agent/session 隔離及並行鎖、私有索引隔離已測。MCP 網路入口屬單一操作者；外部 MCP 工具為共享能力。 |
| S2.10 | 二 | 把課程案例變成可執行的新架構範例 | 部分完成 | 01–03 已改用共享 factory/ConversationManager，但仍強制要求 DashScope Key，阻擋離線及通用 API 配置。04 與 02 的 MCP 模式可執行。F04 |
| S3.1 | 三 | 自動識別 System Prompt/Few-shot | 部分完成 | 目前接受操作者明確配置；未配置的 system 被拒絕，沒有自動識別 few-shot 機制。F01 |
| S3.2 | 三 | System/Few-shot 固定前綴及可重用策略 | 符合固定前綴要求 | 前綴冪等、避免雙份 system、工具按名稱排序；摘要在固定前綴後。實際後端命中率未驗證。 |
| S3.3 | 三 | 歷史過長時使用 LlamaIndex 摘要 | 部分完成 | SummaryIndex + tree_summarize 已實作且注入 MockLLM 測試通過；正常 API 啟動沒有配置 summary_llm，預設使用首尾摘錄。F02 |
| S3.4 | 三 | 保留關鍵資訊；原文稱為無損壓縮 | 已修正承諾；資訊保留待驗證 | 文件正確承認摘要有損，但未提供關鍵事實保留驗收；探測中的中段訂單 ID 被首尾摘錄丟失。原始歷史也只保留最近 64 輪。F02 |
| S3.5 | 三 | 優化流程相容 Streaming | 符合介面要求 | invoke/stream 共用 prepare；真實 model delta、取消不提交、97 段 HTTP 串流與 DONE 通過。摘要仍會增加首 token 前延遲。 |
| S3.6 | 三 | ContextOptimizer 模組與單元測試 | 已完成基礎；驗收覆蓋需補強 | 7 個 optimizer/summary 測試通過；仍缺少關鍵事實保留、工具迴圈超預算及範例啟動的回歸測試。F02/F03/F04 |
| S3.7 | 三 | README 效率說明與效能文件 | 符合 | README/docs/kv-cache.md 說明前綴重用、摘要成本、byte 估算與模型 token 區別；benchmark 可重現。 |
| S3.8 | 三 | 推理加速感知，而非直接操作 GPU KV | 符合修正後的定位 | 提供應用端穩定前綴/歷史預算；沒有宣稱直接管理顯存。工具結果與 schema 不在完整預算內，不能當成每次模型呼叫的上限保證。F03 |
| S4.1 | 四 | README 一句話價值主張 | 符合 | 首段包含 MCP、LangChain/LlamaIndex 雙引擎與穩定上下文前綴。 |
| S4.2 | 四 | 與一般 LangChain 腳本的架構比較 | 符合 | 比較表及雙區塊 Mermaid；文件避免誤稱 LangChain 本身沒有這些能力。 |
| S4.3 | 四 | Quick Start 部署帶 MCP 的 Agent | 本機流程通過；可攜性待修正 | smoke 與 examples.04_mcp_client 本輪可重現；README 開頭固定本機 D: 路徑。首次依賴安裝及其他環境的五分鐘上限未驗證。F07 |
| S4.4 | 四 | 效能基準占位欄位 | 符合 | GPU KV hit rate、TTFT、tokens/sec 均保留 null/待實測，沒有把 byte 縮減誤當 GPU 加速。 |
| S4.5 | 四 | 開發者筆記：課程來源與個人延伸 | 內容符合；路徑需修正 | developer-notes.md 區分課程概念與整合設計，來源筆記檔名引用不符實際檔名。F07 |
| S4.6 | 四 | GitHub Actions 自動測 MCP 與程式品質 | 符合配置要求；雲端未執行 | 父層及獨立專案工作流程皆可解析，含 Windows/Linux × Python 3.11/3.12/3.13、ruff/pytest/HTTP/benchmark/build。 |
| S4.7 | 四 | GitHub 開源作品集發布 | 本機包裝完成；公開發布未執行 | 目前根目錄及 agent-platform 均無 .git/remote；沒有 GitHub 推送或雲端 CI 證據。課程改寫部分的授權狀態尚未確認。 |
| S4.8 | 四 | source distribution/wheel 交付 | 內容通過；驗證邊界及報告需整理 | wheel 32 檔、sdist 59 檔含示範知識庫且排除狀態/快取；sdist 內 packaging-check.json 與目前報告不一致。全新環境離線安裝因依賴快取不足未完成。F10 |
| T1 | 追加 | 把裡面的簡體註解換成繁體 | 新平臺 Python 已完成；全目錄未完成 | 現有 annotation-localization 只涵蓋 35 個新平臺 Python 檔；全目錄仍有 20 檔共 214 個候選註解/docstring 區塊需轉換。F05 |
| T2 | 追加 | 轉換不修改可執行程式 | 專用轉換器符合；根目錄腳本不符合 | localize_annotations 有 AST 比對；translate_all.py 則會改寫全部文字內容且沒有 AST 保護。沒有證據證明其已執行，本輪未執行。F06 |

## 本輪重新驗證的結果

| 驗證 | 本輪結果 | 可支持的結論 |
| --- | --- | --- |
| 完整 pytest | 35 passed；0 failed/error；6 個棄用警告；約 9.93 秒 | 離線整合與已寫的測試通過；不代表所有原始需求都有測試 |
| Ruff check / format | 均通過 | 程式品質規則符合；不等於型別完整 |
| 鎖檔 | 139 個 package 記錄；lock --check --offline 通過；當前分支零版本差異 | 現有 Python 3.12 環境與鎖檔一致；139 含其他 Python 分支記錄 |
| 原生 MCP | stdio / SSE / Streamable HTTP 的握手、tool、resource、prompt、Agent 呼叫通過 | 不是只列工具名稱的假整合 |
| API → 外部 MCP → Agent → invoke/stream | 新增離線探測：載入 4 個 namespaced 診斷工具，invoke/stream 均 200 且取得 <1ms 模擬結果及 DONE | 外部 MCP 適配路徑可執行；使用可選遠端工具的確定性探測模型，沒有驗證真實 LLM 選擇工具 |
| 真正 HTTP 冒煙 | 認證、混合檢索、session follow-up 通過；97 段文字 delta 及 DONE | 本機 Uvicorn 可以使用，不是只有 TestClient 結果 |
| 上下文量測 | 29,572 → 1,198；配置預算 1,200；前綴/最新問題保留 | UTF-8 byte/framing 估算，不是 GPU 命中率或實際 token 數 |
| 前綴辨識探測 | 未配置 system 不被自動識別 | 自動識別仍缺少 |
| 摘錄資訊保留探測 | 中段 CRITICAL_ORDER_ID_98765 未保留 | 關鍵資訊不能視為已保證保留 |
| 工具迴圈預算探測 | 配置 512；模型兩次輸入估算 187 / 12,203 | 初始優化不能保證後續工具迴圈仍在預算內 |
| 範例 01–03 啟動配置探測 | 離線 + 通用 API 配置仍被 DashScope 檢查阻擋 | 課程範例尚有實際啟動缺口 |
| wheel/sdist | 32 / 59 檔；知識庫完整；未包含私人狀態/依賴快取；程式 payload 目前相同 | 包內容可以交付；sdist 的包裝報告另有版本不一致 |
| 全新 wheel 環境 | 已嘗試離線安裝，因依賴 wheel 快取不足未完成 | 不宣稱乾淨環境安裝通過，也不能據此說線上安裝有缺陷 |
| 正式 Markdown 連結 | 0 個不存在的本機連結 | 不涵蓋內文中的路徑字串；另外找到 6 處錯誤來源路徑 |

本輪沒有使用真實 chat/embedding API，也沒有 GPU 推理後端、GitHub 發布或 GitHub 雲端矩陣執行。因此不新增供應商品質、KV hit rate、TTFT 或跨作業系統已驗證的主張。原規劃只要求效能占位與 CI 建議的部分，配置與占位本身已符合，不把尚未測 GPU 誤判為缺少物理 KV 優化實作。

## 需要處理的 10 個發現

### F01 · P2 · 前綴固定已實作，自動識別尚未實作

ContextOptimizer 以 system_prefix/few_shot_examples 明確配置；輸入新的 system 訊息會被拒絕。探測 unconfigured_system_auto_identified=false。這是合理的受控介面，但與原規劃的「自動識別」不同，TASKS 的前綴完成列沒有列出此差異。

程式證據：[agent-platform/core/cache_optimizer/optimizer.py:39](<D:/github project/LangChain/agent-platform/core/cache_optimizer/optimizer.py:39>)；[agent-platform/TASKS.md:17](<D:/github project/LangChain/agent-platform/TASKS.md:17>)。

驗收條件：若維持原需求，加入受信任設定或獨立解析流程，辨識並凍結前綴；測試 few-shot 不重複、不被摘要移動。若選擇明確配置，需把需求與任務狀態如實改寫。

### F02 · P1 · 語義摘要尚未接入預設 API，關鍵資訊保留未達驗收

AgentRuntime 的預設 configs 沒有 summary_llm；正常模型環境設定也沒有把 LlamaIndex LLM 注入這個欄位。未配置時 summarize_texts 使用首尾摘錄。額外探測把 CRITICAL_ORDER_ID_98765 放在舊歷史中段，100 字元摘要未保留該事實。注入摘要分支有測試，但只驗證非空與長度；生成結果仍直接以字元截斷。

程式證據：[agent-platform/core/orchestrator/runtime.py:102](<D:/github project/LangChain/agent-platform/core/orchestrator/runtime.py:102>)；[agent-platform/core/data_engine/compression.py:8](<D:/github project/LangChain/agent-platform/core/data_engine/compression.py:8>)；[agent-platform/tests/test_cache_optimizer.py:100](<D:/github project/LangChain/agent-platform/tests/test_cache_optimizer.py:100>)。

驗收條件：為 API 提供可重現的摘要模型配置；增加數值、姓名、約束、決策的保留驗收。保留「有損摘要」的誠實描述；原始文字或結構化關鍵事實的儲存策略需另有明確期限。

### F03 · P1 · 上下文預算只檢查工具迴圈開始前

runtime.prepare 只在整次 invoke/stream 開始前執行，之後 LangChain 的模型→工具→模型迴圈沒有重新套用預算。以配置預算 512 的同一個 UTF-8 byte/framing 估算，第一個模型輸入是 187，加入 12,000 字元工具回傳後第二次是 12,203。這證明應用端配置預算可以被工具結果突破；此數字不是實際 tokenizer token 數，也不等於已觀察到供應商視窗錯誤。

程式證據：[agent-platform/core/orchestrator/runtime.py:122](<D:/github project/LangChain/agent-platform/core/orchestrator/runtime.py:122>)；[agent-platform/core/orchestrator/agent.py:66](<D:/github project/LangChain/agent-platform/core/orchestrator/agent.py:66>)；[agent-platform/core/cache_optimizer/optimizer.py:30](<D:/github project/LangChain/agent-platform/core/cache_optimizer/optimizer.py:30>)。

驗收條件：在每次模型呼叫前計算完整輸入與保留輸出空間；對大型工具結果做有界處理，保留 tool_call ID 配對；用已知 tokenizer 與長工具輸出驗證 invoke/stream。

### F04 · P1 · 三個移植範例仍被 DashScope 專用 Key 檢查阻擋

examples/01、02 的一般 Agent 模式、03 的 main 均先呼叫 _require_api_key，只接受 DASHSCOPE_API_KEY。探測在 AGENT_PLATFORM_DEMO=1 且提供通用 LLM_API_KEY 的設定下，三者仍 SystemExit。共享 factory 已支援離線/通用相容 API，這個舊檢查使範例與平台配置不一致。02 的 --mcp 與 04 可執行。

程式證據：[agent-platform/examples/01_toolchain_agent.py:163](<D:/github project/LangChain/agent-platform/examples/01_toolchain_agent.py:163>)；[agent-platform/examples/02_network_diagnosis.py:132](<D:/github project/LangChain/agent-platform/examples/02_network_diagnosis.py:132>)；[agent-platform/examples/03_memory_conversation.py:33](<D:/github project/LangChain/agent-platform/examples/03_memory_conversation.py:33>)。

驗收條件：沿用共享模型配置的檢查；驗證離線啟動及通用供應商配置不需要 DashScope。若要示範工具選擇，離線模型還需相應工具行為，不能只用回音輸出代替工具鏈驗收。

### F05 · P2 · 繁體化只完成新平臺 Python 範圍

全目錄註解掃描仍在 20 個檔案發現 214 個轉換候選區塊：原始課程 .py、notebook/checkpoint、筆記內程式註解，以及 agent-platform/.gitignore。新平臺 Python 註解/docstring 在現有 NLS/詞彙轉換規則下沒有剩餘候選。檔名中的簡體與可執行字串不算註解問題，應保留真實路徑。

程式證據：[agent-platform/.gitignore:10](<D:/github project/LangChain/agent-platform/.gitignore:10>)；[agent-platform/scripts/localize_annotations.py:14](<D:/github project/LangChain/agent-platform/scripts/localize_annotations.py:14>)。

驗收條件：把確認的全目錄範圍納入註解轉換，處理 notebook 的 code cells 及設定檔註解；逐檔比較可執行 AST，保留實際檔名與識別符。214 為區塊數，不是簡體字數，且含 checkpoint 重複內容。

### F06 · P1 · 根目錄 translate_all.py 不符合只改註解的範圍

腳本把完整 .py/.md/.txt 內容交給 OpenCC，再直接覆寫。這會涵蓋 prompt、測試字串、關鍵字及文字中的檔案路徑，且只排除 .venv/.git/__pycache__，未排除 .state/.uv-cache/測試暫存。import 時還會嘗試 pip 安裝依賴。此為目前腳本行為的檢查結果，不能據此推斷它已經被執行或誰執行過。

程式證據：[translate_all.py:4](<D:/github project/LangChain/translate_all.py:4>)；[translate_all.py:25](<D:/github project/LangChain/translate_all.py:25>)；[translate_all.py:34](<D:/github project/LangChain/translate_all.py:34>)。

驗收條件：停用或改成限於註解/docstring 的安全轉換入口；明確排除執行環境與快取，不在 import 時安裝依賴，先解析並比對 AST 再寫入。

### F07 · P2 · 文件含不存在的來源路徑及少數實作不一致

asset-audit.md 有 5 處、developer-notes.md 有 1 處把實際簡體檔名寫成繁體，合計 6 處文字引用不存在。Markdown 的正式連結本輪全部可解析，因此「連結零失敗」並不能涵蓋這些來源文字路徑。另外 README Quick Start 固定本機 D: 路徑；02 範例 docstring 稱可直接經 register_tools 掛載診斷工具，但該函數目前只註冊平台三個工具。

程式證據：[agent-platform/docs/asset-audit.md:7](<D:/github project/LangChain/agent-platform/docs/asset-audit.md:7>)；[agent-platform/docs/developer-notes.md:7](<D:/github project/LangChain/agent-platform/docs/developer-notes.md:7>)；[agent-platform/README.md:47](<D:/github project/LangChain/agent-platform/README.md:47>)；[agent-platform/examples/02_network_diagnosis.py:12](<D:/github project/LangChain/agent-platform/examples/02_network_diagnosis.py:12>)；[agent-platform/mcp_server/registry.py:17](<D:/github project/LangChain/agent-platform/mcp_server/registry.py:17>)。

驗收條件：以實際存在的檔案路徑建立來源連結；公開 Quick Start 改成可攜的專案路徑；修正文句或實際加入診斷工具註冊介面。

### F08 · P2 · 完整型別註解要求仍有四處缺口

非測試的新平台 Python 介面有 4 處缺漏：01 的 process_task(agent)、02 的 diagnose(agent) 未註解 agent；mcp_server/__init__.py 與 platform_api/__init__.py 的 __getattr__ 未註解回傳。Ruff 通過不代表型別完整，現有 CI 也未執行 mypy/pyright；graph/engine/session 大量使用 Any。

程式證據：[agent-platform/examples/01_toolchain_agent.py:174](<D:/github project/LangChain/agent-platform/examples/01_toolchain_agent.py:174>)；[agent-platform/examples/02_network_diagnosis.py:165](<D:/github project/LangChain/agent-platform/examples/02_network_diagnosis.py:165>)；[agent-platform/mcp_server/__init__.py:6](<D:/github project/LangChain/agent-platform/mcp_server/__init__.py:6>)；[agent-platform/platform_api/__init__.py:6](<D:/github project/LangChain/agent-platform/platform_api/__init__.py:6>)。

驗收條件：補齊公開介面的型別，為可交換引擎/Agent 定義適當協定；針對核心程式加入適當型別檢查。舊課程及測試的型別狀態需與核心介面分開記錄。

### F09 · P2 · TASKS 的完成定義比原規劃寬

TASKS.md 首段稱功能/文件完成，但將明確配置前綴對應到原規劃的自動識別，將可注入摘要對應到一般啟動流程，以及將新平台 Python 範圍的繁體化對應到全目錄需求時，都會高估完成程度。它對供應商/GPU/CI/推送未驗證的說明則是正確的。

程式證據：[agent-platform/TASKS.md:3](<D:/github project/LangChain/agent-platform/TASKS.md:3>)；[agent-platform/TASKS.md:17](<D:/github project/LangChain/agent-platform/TASKS.md:17>)；[agent-platform/TASKS.md:18](<D:/github project/LangChain/agent-platform/TASKS.md:18>)；[agent-platform/TASKS.md:27](<D:/github project/LangChain/agent-platform/TASKS.md:27>)。

驗收條件：讓任務列與原始需求逐項對應，明列部分完成、配置完成、待驗證及範圍修正；不能以 35 項測試通過代替所有需求的驗收。

### F10 · P3 · sdist 中的包裝驗證報告與目前報告不一致

wheel 32 個成員與目前檔案逐 byte 相同；sdist 59 個成員中，只有 reports/packaging-check.json 與工作目錄不同，程式內容相同。屬於證據版本不一致，沒有證據顯示 wheel 程式過期。新增本輪稽核輸出也尚未在既有發行包內。

程式證據：[agent-platform/reports/packaging-check.json:2](<D:/github project/LangChain/agent-platform/reports/packaging-check.json:2>)；[agent-platform/pyproject.toml:51](<D:/github project/LangChain/agent-platform/pyproject.toml:51>)。

驗收條件：確定最終報告後重新建置並核對 manifest；將建置後的外部驗證報告與被打包內容的版本關係明確分開，避免報告自我更新造成歧異。

## 來源路徑核對

| 文件 | 行 | 文件寫法 | 是否存在 |
| --- | --- | --- | --- |
| agent-platform/docs/asset-audit.md | 7 | CASE-工具鏈組合/1-simple_toolchain.py | 否 |
| agent-platform/docs/asset-audit.md | 8 | CASE-搭建故障診斷Agent/2-network_diagnosis_agent.py | 否 |
| agent-platform/docs/asset-audit.md | 9 | CASE-LangChain使用/4-ConversationChain.py | 是 |
| agent-platform/docs/asset-audit.md | 10 | CASE-工具鏈組合/3-lcel-demo.py | 否 |
| agent-platform/docs/asset-audit.md | 11 | 筆記20260727.txt | 否 |
| agent-platform/docs/asset-audit.md | 12 | 1-LangChain：多任務應用開發.pdf | 否 |
| agent-platform/docs/developer-notes.md | 7 | 筆記20260727.txt | 否 |

## 未完成的繁體註解範圍

以下是現有 NLS/台灣詞彙規則仍會轉換的註解/docstring 區塊。Notebook 的數字包含 code cell 註解；checkpoint 與正式 notebook 分開列出。此掃描不把實際簡體檔名當成要改名的指令，也沒有修改可執行字串。

| 檔案 | 候選區塊 |
| --- | --- |
| CASE-LangChain使用/.ipynb_checkpoints/1-LLMChain-checkpoint.ipynb | 5 |
| CASE-LangChain使用/.ipynb_checkpoints/2-LLMChain-checkpoint.ipynb | 5 |
| CASE-LangChain使用/.ipynb_checkpoints/3-LLMChain-checkpoint.ipynb | 7 |
| CASE-LangChain使用/.ipynb_checkpoints/4-ConversationChain-checkpoint.ipynb | 8 |
| CASE-LangChain使用/.ipynb_checkpoints/5-product_llm-checkpoint.py | 11 |
| CASE-LangChain使用/1-LLMChain.ipynb | 5 |
| CASE-LangChain使用/1-LLMChain.py | 7 |
| CASE-LangChain使用/2-LLMChain.ipynb | 5 |
| CASE-LangChain使用/2-LLMChain.py | 5 |
| CASE-LangChain使用/3-LLMChain.ipynb | 7 |
| CASE-LangChain使用/3-LLMChain.py | 8 |
| CASE-LangChain使用/4-ConversationChain.ipynb | 8 |
| CASE-LangChain使用/4-ConversationChain.py | 8 |
| CASE-LangChain使用/5-product_llm.py | 11 |
| CASE-工具链组合/1-simple_toolchain.py | 27 |
| CASE-工具链组合/2-simple_toolchain.py | 26 |
| CASE-工具链组合/3-lcel-demo.py | 8 |
| CASE-搭建故障诊断Agent/2-network_diagnosis_agent.py | 42 |
| agent-platform/.gitignore | 4 |
| 笔记20260727.txt | 7 |

## 全部 84 個檔案的核對表

表格列出每個檔案的角色與問題對應；CSV 另含完整 SHA-256 與結構檢查。沒有問題編號只表示未發現該檔的具體缺口，並不表示其所屬整個階段都已完整驗收。

| 檔案 | 類別 | 規劃對應 | 問題 | 核對結果 |
| --- | --- | --- | --- | --- |
| .github/workflows/agent-platform.yml | 父層 CI | S4.6 | — | 整個 LangChain 目錄發布時的 CI；配置可解析，尚未在 GitHub 執行 |
| 1-LangChain：多任务应用开发.pdf | 課程來源 | S1.1/S1.2/T1 | — | 原始 64 頁簡報；全頁擷取檢閱，不納入平台發行包 |
| CASE-LangChain使用/.ipynb_checkpoints/1-LLMChain-checkpoint.ipynb | 課程來源 | S1.1/S1.2/T1 | F05 | 課程備份參考；結構/程式區塊已查，沒有作為新平台執行入口 |
| CASE-LangChain使用/.ipynb_checkpoints/2-LLMChain-checkpoint.ipynb | 課程來源 | S1.1/S1.2/T1 | F05 | 課程備份參考；結構/程式區塊已查，沒有作為新平台執行入口 |
| CASE-LangChain使用/.ipynb_checkpoints/3-LLMChain-checkpoint.ipynb | 課程來源 | S1.1/S1.2/T1 | F05 | 課程備份參考；結構/程式區塊已查，沒有作為新平台執行入口 |
| CASE-LangChain使用/.ipynb_checkpoints/4-ConversationChain-checkpoint.ipynb | 課程來源 | S1.1/S1.2/T1 | F05 | 課程備份參考；結構/程式區塊已查，沒有作為新平台執行入口 |
| CASE-LangChain使用/.ipynb_checkpoints/5-product_llm-checkpoint.py | 課程來源 | S1.1/S1.2/T1 | F05 | 課程備份參考；結構/程式區塊已查，沒有作為新平台執行入口 |
| CASE-LangChain使用/1-LLMChain.ipynb | 課程來源 | S1.1/S1.2/T1 | F05 | 原始 notebook；JSON/所有程式區塊已查，未使用付費憑證重新執行 |
| CASE-LangChain使用/1-LLMChain.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-LangChain使用/2-LLMChain.ipynb | 課程來源 | S1.1/S1.2/T1 | F05 | 原始 notebook；JSON/所有程式區塊已查，未使用付費憑證重新執行 |
| CASE-LangChain使用/2-LLMChain.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-LangChain使用/3-LLMChain.ipynb | 課程來源 | S1.1/S1.2/T1 | F05 | 原始 notebook；JSON/所有程式區塊已查，未使用付費憑證重新執行 |
| CASE-LangChain使用/3-LLMChain.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-LangChain使用/4-ConversationChain.ipynb | 課程來源 | S1.1/S1.2/T1 | F05 | 原始 notebook；JSON/所有程式區塊已查，未使用付費憑證重新執行 |
| CASE-LangChain使用/4-ConversationChain.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-LangChain使用/5-product_llm.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-LangChain使用/requirements.txt | 課程來源 | S1.1/S1.2/T1 | — | 保留課程依賴；新平台另外使用 uv.lock，不混用兩套環境 |
| CASE-工具链组合/1-simple_toolchain.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-工具链组合/2-simple_toolchain.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-工具链组合/3-lcel-demo.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-工具链组合/requirements.txt | 課程來源 | S1.1/S1.2/T1 | — | 保留課程依賴；新平台另外使用 uv.lock，不混用兩套環境 |
| CASE-搭建故障诊断Agent/2-network_diagnosis_agent.py | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程參考；語法通過，未作為新平台 API/MCP 實作 |
| CASE-搭建故障诊断Agent/requirements.txt | 課程來源 | S1.1/S1.2/T1 | — | 保留課程依賴；新平台另外使用 uv.lock，不混用兩套環境 |
| agent-platform/.env.example | 環境模板 | S2.9/S4.3 | — | 變數名稱對應實作；未配置摘要模型的正常啟動入口 |
| agent-platform/.github/workflows/ci.yml | 獨立專案 CI | S4.6 | — | agent-platform 作為 repo 根目錄時的工作流程，尚無雲端執行證據 |
| agent-platform/.gitignore | 忽略規則 | T1/S4.8 | F05 | 狀態/憑證/快取規則已設；仍有簡體註解 |
| agent-platform/LICENSE | 授權聲明 | S4.7 | — | 存在 MIT 聲明；不能藉此證明所有課程改寫素材的授權已確認 |
| agent-platform/README.md | 作品集入口 | S4.1–S4.4 | F07 | 價值主張/比較圖/啟動/指標占位已提供；公開路徑可攜性需整理 |
| agent-platform/TASKS.md | 任務表 | S1/S2/S3/S4/T1 | F01,F09 | 原規劃追蹤表；部分完成定義需依本報告修正 |
| agent-platform/core/__init__.py | 套件結構 | S2.7/S4.8 | — | 合法套件入口；空 __init__.py 不構成缺漏 |
| agent-platform/core/cache_optimizer/__init__.py | 上下文 | S3.1–S3.8 | — | 固定前綴與歷史預算；自動識別及完整工具迴圈預算尚未完成 |
| agent-platform/core/cache_optimizer/optimizer.py | 上下文 | S3.1–S3.8 | F01,F03 | 固定前綴與歷史預算；自動識別及完整工具迴圈預算尚未完成 |
| agent-platform/core/data_engine/__init__.py | 資料引擎 | S2.1/S2.8/S3.3 | — | 獨立 LlamaIndex、向量+BM25+RRF 及可注入摘要 |
| agent-platform/core/data_engine/compression.py | 資料引擎 | S2.1/S2.8/S3.3 | F02 | 獨立 LlamaIndex、向量+BM25+RRF 及可注入摘要 |
| agent-platform/core/data_engine/engine.py | 資料引擎 | S2.1/S2.8/S3.3 | — | 獨立 LlamaIndex、向量+BM25+RRF 及可注入摘要 |
| agent-platform/core/data_engine/retrieval.py | 資料引擎 | S2.1/S2.8/S3.3 | — | 獨立 LlamaIndex、向量+BM25+RRF 及可注入摘要 |
| agent-platform/core/orchestrator/__init__.py | 編排 | S2.8/S2.9/S3.5 | — | 共享 Agent factory/runtime、按 tenant/agent/session 隔離與模型串流 |
| agent-platform/core/orchestrator/agent.py | 編排 | S2.8/S2.9/S3.5 | F03 | 共享 Agent factory/runtime、按 tenant/agent/session 隔離與模型串流 |
| agent-platform/core/orchestrator/demo.py | 編排 | S2.8/S2.9/S3.5 | — | 確定性離線模型；只測整合，不能代表真實模型品質 |
| agent-platform/core/orchestrator/memory.py | 編排 | S2.8/S2.9/S3.5 | — | 教學 session 記憶；有棄用警告，不具 API 的租戶隔離或預算 |
| agent-platform/core/orchestrator/runtime.py | 編排 | S2.8/S2.9/S3.5 | F02,F03 | 共享 Agent factory/runtime、按 tenant/agent/session 隔離與模型串流 |
| agent-platform/docs/architecture.md | 設計文件 | S1.1–S1.4/S3.7/S4.5 | — | 內容已核對程式；來源路徑與少數完成定義需修正 |
| agent-platform/docs/asset-audit.md | 設計文件 | S1.1–S1.4/S3.7/S4.5 | F07 | 內容已核對程式；來源路徑與少數完成定義需修正 |
| agent-platform/docs/developer-notes.md | 設計文件 | S1.1–S1.4/S3.7/S4.5 | F07 | 內容已核對程式；來源路徑與少數完成定義需修正 |
| agent-platform/docs/kv-cache.md | 設計文件 | S1.1–S1.4/S3.7/S4.5 | — | 內容已核對程式；來源路徑與少數完成定義需修正 |
| agent-platform/examples/01_toolchain_agent.py | 新範例 | S2.10/S4.3/T1 | F04,F08 | 課程改寫或 MCP 客戶端示範；01–03 的模型配置仍不一致 |
| agent-platform/examples/02_network_diagnosis.py | 新範例 | S2.10/S4.3/T1 | F04,F07,F08 | 課程改寫或 MCP 客戶端示範；01–03 的模型配置仍不一致 |
| agent-platform/examples/03_memory_conversation.py | 新範例 | S2.10/S4.3/T1 | F04 | 課程改寫或 MCP 客戶端示範；01–03 的模型配置仍不一致 |
| agent-platform/examples/04_mcp_client.py | 新範例 | S2.10/S4.3/T1 | — | 課程改寫或 MCP 客戶端示範；01–03 的模型配置仍不一致 |
| agent-platform/examples/__init__.py | 新範例 | S2.10/S4.3/T1 | — | 課程改寫或 MCP 客戶端示範；01–03 的模型配置仍不一致 |
| agent-platform/examples/knowledge/cache.md | 示範知識庫 | S2.8/S4.3 | — | 自撰示範資料；已打包並透過真實檢索驗證 |
| agent-platform/examples/knowledge/diagnosis.md | 示範知識庫 | S2.8/S4.3 | — | 自撰示範資料；已打包並透過真實檢索驗證 |
| agent-platform/examples/knowledge/platform.md | 示範知識庫 | S2.8/S4.3 | — | 自撰示範資料；已打包並透過真實檢索驗證 |
| agent-platform/mcp_server/README.md | MCP | S2.1–S2.3/S2.6 | — | Server/Client、三種傳輸、schema adapter 與 resource/prompt |
| agent-platform/mcp_server/__init__.py | MCP | S2.1–S2.3/S2.6 | F08 | Server/Client、三種傳輸、schema adapter 與 resource/prompt |
| agent-platform/mcp_server/client.py | MCP | S2.1–S2.3/S2.6 | — | Server/Client、三種傳輸、schema adapter 與 resource/prompt |
| agent-platform/mcp_server/registry.py | MCP | S2.1–S2.3/S2.6 | F07 | Server/Client、三種傳輸、schema adapter 與 resource/prompt |
| agent-platform/mcp_server/server.py | MCP | S2.1–S2.3/S2.6 | — | Server/Client、三種傳輸、schema adapter 與 resource/prompt |
| agent-platform/platform_api/__init__.py | API/Key | S2.9/S3.5 | F08 | FastAPI 路由、雜湊 Key 管理、權限與 SSE；單程序狀態 |
| agent-platform/platform_api/api.py | API/Key | S2.9/S3.5 | — | FastAPI 路由、雜湊 Key 管理、權限與 SSE；單程序狀態 |
| agent-platform/platform_api/auth.py | API/Key | S2.9/S3.5 | — | FastAPI 路由、雜湊 Key 管理、權限與 SSE；單程序狀態 |
| agent-platform/pyproject.toml | 依賴/包裝 | S2.4/S2.7/S4.8 | F10 | 配置及鎖檔通過；有跨 Python 分支，按當前分支核對沒有版本差異 |
| agent-platform/reports/annotation-localization.json | 既有證據 | S3.6/S3.7/S4.8/T1 | — | 既有結果與本輪核對；範圍/時間/來源及打包報告版本要分清 |
| agent-platform/reports/context-benchmark.json | 既有證據 | S3.6/S3.7/S4.8/T1 | — | 既有結果與本輪核對；範圍/時間/來源及打包報告版本要分清 |
| agent-platform/reports/http-smoke.json | 既有證據 | S3.6/S3.7/S4.8/T1 | — | 既有結果與本輪核對；範圍/時間/來源及打包報告版本要分清 |
| agent-platform/reports/junit.xml | 既有證據 | S3.6/S3.7/S4.8/T1 | — | 既有結果與本輪核對；範圍/時間/來源及打包報告版本要分清 |
| agent-platform/reports/packaging-check.json | 既有證據 | S3.6/S3.7/S4.8/T1 | F10 | 既有結果與本輪核對；範圍/時間/來源及打包報告版本要分清 |
| agent-platform/reports/verification.md | 既有證據 | S3.6/S3.7/S4.8/T1 | — | 既有結果與本輪核對；範圍/時間/來源及打包報告版本要分清 |
| agent-platform/scripts/benchmark_context.py | 驗證/啟動腳本 | S3.7/S4.3/T1/T2 | — | HTTP/上下文量測本輪重現；PowerShell 語法通過；轉換器只處理平台 Python |
| agent-platform/scripts/localize_annotations.py | 驗證/啟動腳本 | S3.7/S4.3/T1/T2 | F05 | HTTP/上下文量測本輪重現；PowerShell 語法通過；轉換器只處理平台 Python |
| agent-platform/scripts/smoke.py | 驗證/啟動腳本 | S3.7/S4.3/T1/T2 | — | HTTP/上下文量測本輪重現；PowerShell 語法通過；轉換器只處理平台 Python |
| agent-platform/scripts/start-demo.ps1 | 驗證/啟動腳本 | S3.7/S4.3/T1/T2 | — | HTTP/上下文量測本輪重現；PowerShell 語法通過；轉換器只處理平台 Python |
| agent-platform/tests/__init__.py | 測試 | S3.6/S4.6 | — | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/tests/conftest.py | 測試 | S3.6/S4.6 | — | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/tests/test_cache_optimizer.py | 測試 | S3.6/S4.6 | F02 | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/tests/test_data_engine.py | 測試 | S3.6/S4.6 | — | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/tests/test_examples.py | 測試 | S3.6/S4.6 | — | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/tests/test_mcp_compat.py | 測試 | S3.6/S4.6 | — | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/tests/test_orchestrator.py | 測試 | S3.6/S4.6 | — | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/tests/test_platform_api.py | 測試 | S3.6/S4.6 | — | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/tests/test_runtime.py | 測試 | S3.6/S4.6 | — | 本輪 35 項套件測試全部通過；現有覆蓋不能證明所有原規劃完成 |
| agent-platform/uv.lock | 依賴/包裝 | S2.4/S2.7/S4.8 | — | 配置及鎖檔通過；有跨 Python 分支，按當前分支核對沒有版本差異 |
| translate_all.py | 根目錄轉換腳本 | T1/T2 | F06 | 全內容轉換，超出只改註解的範圍；本輪未執行 |
| 笔记20260727.txt | 課程來源 | S1.1/S1.2/T1 | F05 | 原始課程筆記；對應上下文/工具/MCP/記憶的設計動機 |

## 修正與後續驗收順序

1. 先補摘要正常配置及關鍵事實保留驗收，並處理模型每次呼叫的完整輸入預算；維持工具呼叫與結果配對。

2. 修正三個範例的模型配置檢查；讓離線演示也能實際驗證它承諾的工具行為。

3. 明確完成自動前綴識別，或把需求改成受信任的固定配置；補齊型別。

4. 完成全目錄註解轉換並保護 AST，停用全內容翻譯入口；修復來源路徑及任務狀態。

5. 定稿報告後重新打包，驗證乾淨環境及實際 CI；若要公開，先完成 repository/remote 與來源範圍確認。


GPU PagedAttention、分散式會話、配額及商用組織管理不是本輪原規劃的必須程式交付項；應另外列為擴充，不用來掩蓋本報告指出的具體缺口。

