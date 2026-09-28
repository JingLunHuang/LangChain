# 四階段任務清單與驗收表

更新日期：2026-09-28。功能、文件與本機打包已完成；未驗證的供應商／GPU 實驗及未執行的 GitHub 推送另列，不當成完成的成果。

| 階段 | 任務 | 狀態 | 交付與驗收 |
| --- | --- | --- | --- |
| 一 | 閱讀原始程式、筆記及簡報 | 完成 | [資產盤點](docs/asset-audit.md)：三個主要案例、LCEL、筆記與 64 頁簡報 |
| 一 | 核心功能、優缺點與可重用模組 | 完成 | 資產盤點與 Kimi 修復紀錄；原始素材保留 |
| 一 | 五層架構 Mermaid 與框架分工 | 完成 | [架構文件](docs/architecture.md)，涵蓋接入、編排、資料、協議、效能 |
| 一 | MCP 與 KV Cache 技術選型 | 完成 | 官方 SDK v1 版本界限、LlamaIndex RRF、應用層與推理引擎責任界線 |
| 二 | LlamaIndex QueryEngine 工具封裝 | 完成 | [engine.py](core/data_engine/engine.py)，可由 MCP 與 LangChain 呼叫 |
| 二 | 真正的混合檢索 | 完成 | VectorStoreIndex + BM25 + RRF，答案附來源；實際 QueryEngine 測試通過 |
| 二 | MCP Server 與 Client | 完成 | [MCP 文件](mcp_server/README.md)：stdio、SSE、Streamable HTTP 與 schema adapter |
| 二 | Resource／Prompt 擴充入口 | 完成 | info://server 與 diagnose，三種傳輸的讀取／取得測試通過 |
| 二 | uv、型別化介面、非同步 | 完成 | pyproject.toml、uv.lock；正常匯入，不覆寫標準函式庫 |
| 二 | API Key、租戶與多 Agent 路由 | 完成 | Key 發行／列表／撤銷、租戶私有索引、tenant／agent／session 隔離 |
| 三 | System／few-shot 穩定前綴 | 完成 | ContextOptimizer 前綴冪等，factory 不重複加 system，工具排序固定 |
| 三 | 歷史壓縮與最新問題保護 | 完成 | LlamaIndex 摘要可注入；未配置時首尾摘錄；最新問題不能放入時回報 413 |
| 三 | 修正「無損」的錯誤承諾 | 完成 | [KV 文件](docs/kv-cache.md)：摘要有損；原始歷史另存，保存期限明確 |
| 三 | 真正串流且沿用相同優化流程 | 完成 | LangChain model message delta；取消不保存部分答案；HTTP 實測 97 段與 DONE |
| 三 | 單元、隔離與整合測試 | 完成 | 35 項全通過；[驗收紀錄](reports/verification.md) |
| 三 | 效能文件與量測腳本 | 完成 | byte 預算估算 29,572 → 1,198；GPU KV 指標保留待測欄位 |
| 四 | README、比較圖、Quick Start | 完成 | [README](README.md)、MCP 示範、[本機啟動腳本](scripts/start-demo.ps1) |
| 四 | 課程來源與個人延伸筆記 | 完成 | [開發者筆記](docs/developer-notes.md)，區分教學起點與整合設計 |
| 四 | GitHub Actions | 完成配置 | Windows／Linux × Python 3.11／3.12／3.13；MCP、lint、test、build 納入流程 |
| 四 | source distribution／wheel | 完成本機驗證 | dist/；知識庫已打包，未包含 .state、憑證、快取或完整課程 PDF |
| 追加 | 程式註解與 docstring 繁體化 | 完成 | 檢查 35 個 Python 檔，8 檔共 20 處轉換；可執行 AST 不變，測試仍 35/35 |

## 目前不列為已驗證成果

| 項目 | 現況與條件 |
| --- | --- |
| 真實 chat／embedding API | 未使用私人供應商憑證；可依 .env.example 配置 |
| GPU KV hit rate、TTFT、tokens/sec | 未連接 GPU 推理後端；文件提供實測方法與待測欄位 |
| 公開 GitHub 推送與 GitHub 雲端 CI | 目前目錄沒有 Git repository／remote，未推送；CI 僅完成配置 |
| 商用多租戶規模 | 目前為具隔離的單程序基礎；未提供分散式會話、配額與完整組織權限 |
| 原始課程素材授權 | 原始素材不納入平台發行包；授權需另外確認 |

## 重現驗收

```powershell
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest --junitxml=reports/junit.xml
uv run python -m scripts.smoke
uv run python -m scripts.benchmark_context
uv build
```

所有功能驗收採離線示範模型，不呼叫付費模型。MCP 與 HTTP 測試仍使用真正的協議傳輸、子程序及本機網路服務。
