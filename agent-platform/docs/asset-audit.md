# 既有資產盤點與修復紀錄

盤點日期：2026-09-28。原始課程檔案保留，實作延伸位於 `agent-platform`。

| 資產 | 觀察到的功能 | 可重用部分與問題 | 平臺落點 |
| --- | --- | --- | --- |
| `CASE-工具鏈組合/1-simple_toolchain.py` | 文本分析、格式轉換、行數／查找／替換，使用 create_agent | 工具描述與 schema 可重用；腳本啟動及模型配置與任務耦合，CSV 範例解析簡化 | `examples/01_toolchain_agent.py` 與共享 factory |
| `CASE-搭建故障診斷Agent/2-network_diagnosis_agent.py` | ping、DNS、介面、日誌等四個模擬工具 | 工具串聯概念可重用；所有觀察均是模擬，不能當真實網路證據 | `examples/02_network_diagnosis.py`；stdio log 改至 stderr |
| `CASE-LangChain使用/4-ConversationChain.py` | Prompt、history placeholder、RunnableWithMessageHistory | session_id 記憶可重用；缺少 tenant／agent scope，歷史沒有界限 | 教學 ConversationManager，API 另用具隔離與預算的 AgentRuntime |
| `CASE-工具鏈組合/3-lcel-demo.py` | Runnable、pipe、分支與並行等組合示範 | 輕量編排理念可重用；不需要把兩個框架原始碼合併 | 資料層透過工具合約與 LangChain 連接 |
| `筆記20260727.txt` | 工具與 skill 差異、上下文摘要、MCP 描述成本、短期記憶與快取提問 | 提供設計動機；筆記的討論不是性能實驗 | ContextOptimizer、MCP client、開發者筆記 |
| `1-LangChain：多任務應用開發.pdf`，64 頁 | 課程架構、tools、memory、ReAct、工具鏈、故障診斷、LCEL | 已以 pypdf 擷取文字檢閱；不把完整課程 PDF／全文打包為自己的作品 | 第 5–8、17–21、32–49、50 起的內容作為設計來源 |

簡報同時包含舊式 ReAct 範例與較新的 create_agent／LCEL 介紹；本平臺以安裝版本的公開 API 為準，不照抄已移除的初始化方式。課程中的工具回傳與案例答案是教學素材，不是檢索質量或推理性能基準。

## Kimi 未完成的實際問題

| 原本問題 | 修復結果 |
| --- | --- |
| 頂層 `platform` 覆蓋 Python 標準函式庫，測試需改寫 sys.modules | 改成 `platform_api`，可以正常匯入與使用 Uvicorn |
| 測試在收集時污染共享 sys.modules | 改成正常 import、依賴注入與真正的離線整合測試 |
| 名稱為 hybrid_retrieve，實際只有 VectorStoreIndex | 加入獨立 BM25 Retriever 與 RRF |
| 檢索依賴隱含的 OpenAI Settings / Key | 明確注入模型；離線示範不依賴供應商憑證 |
| optimizer 呼叫摘要時漏掉 max_chars | 統一異步摘要與明確的長度／預算參數 |
| 所謂無損摘要實際截斷尾端 | 改成明確有損摘要，保留原始會話副本並保護最新問題 |
| API 的 session_id 只有回傳，沒有真正帶入歷史 | tenant／agent／session 三者隔離，鎖定會話並提交成功回覆 |
| streaming 缺少實作，一次回傳完整答案 | 實際消費 LangChain model message stream |
| 平臺只有預設可猜的開發 Key | 移除隱含 Key，補上 SQLite 雜湊 Key 發行、列表、撤銷 |
| MCP 只提供 Server，無 Client | 補上三種傳輸的原生 Client 與 schema adapter |
| MCP 工具可由 client 指定本機 docs_path | 移除此參數，目錄由操作者配置 |
| 用動態 exec 組裝 MCP wrapper | 直接註冊帶型別的函數 |
| Windows stdio 首次檢索卡在 NumPy import | 在啟動 stdio reader 前初始化資料層依賴；三種協議測試通過 |
| network-diagnosis MCP 使用不存在的 tool.fn | 改用 StructuredTool.func，日誌不污染 stdout |
| CI 的 MCP job 仍是 TODO，依賴未鎖定 | 三種傳輸測試進入 CI，加入 uv.lock 與 package build |

## 未作為已驗證結果的事項

沒有使用私人供應商 Key；真實 chat／embedding API、vLLM／SGLang 的 GPU 快取命中率與延遲仍需另行測量。未確認原始課程素材的開源授權。父目錄目前不是 Git repository，也沒有 remote，尚未推送至 GitHub。
