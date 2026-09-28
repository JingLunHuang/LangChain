# OmniAgent Platform 🚀
*(English Version below / 英文版在下方)*

**OmniAgent Platform** 是一個專為企業與開發者打造的「生產級開源 Agent 部署框架」。本專案將複雜的 LLM（大型語言模型）應用解耦為模組化、高擴展性的架構，不僅提供靈活的 Agent 邏輯編排，還原生整合了 MCP (Model Context Protocol) 以及針對底層 GPU KV Cache 的最佳化。

---

## 🇹🇼 中文介紹 (Traditional Chinese)

### 為什麼需要這個架構？它解決了什麼痛點？

在當前 AI 應用的開發中，許多開發者在從「實驗室腳本」過渡到「線上生產環境」時，經常會遇到以下痛點：
1. **工具生態無法互通**：大部分 Agent 框架的工具是綁死的，無法在不同系統間輕易共用或外掛。
2. **上下文過長導致記憶體崩潰與高延遲**：當對話輪次增加，無效對話會大量消耗 Token 並破壞 LLM 的前綴快取 (Prefix Cache) 命中率。
3. **單一資料庫檢索品質不佳**：傳統的單純向量檢索 (Vector Search) 容易忽略精確的關鍵字比對。
4. **缺乏多租戶與企業級權限管理**：簡單的腳本無法提供 API Key 隔離、連線並發控制等 SaaS 基本需求。

### OmniAgent 平台能幫你做什麼？

為了徹底解決上述問題，這個通用型架構提供了以下四大核心能力：

* 🔌 **原生支援 MCP (Model Context Protocol)**：本框架本身就是一個強大的 MCP Server，能將內建能力（如檢索、特定診斷工具）暴露給如 Claude Desktop 或 Cursor 等外部工具使用；同時它也是 MCP Client，支援將任何外部標準 MCP Server 瞬間轉化為 Agent 的擴充能力。
* 🧠 **混合檢索增強 (Hybrid RAG)**：摒棄單一框架限制，採用 **LangChain 作為大腦進行任務編排**，並將 **LlamaIndex 封裝為高效能的資料引擎**。內部使用向量檢索 + BM25 的雙路徑搜尋，搭配 RRF (Reciprocal Rank Fusion) 重新排序，提供極致準確的知識召回。
* ⚡ **推理加速感知 (KV-Cache Aware)**：獨創 `ContextOptimizer`，在應用層面固定 System Prompt 與 Few-shot 的前綴位置。這讓底層推理引擎（如 vLLM、SGLang）能完美發揮 PagedAttention 的威力，大幅降低 TTFT（首字延遲）並節省 GPU 算力。當歷史紀錄過長時，還會自動觸發無損語意壓縮。
* 🛡️ **開箱即用的 API 服務**：不再只是 Python 腳本。這是一套建構於 FastAPI 之上的微服務，內建 Token 預算限制、API Key 多租戶權限隔離、安全的會話記憶體鎖定機制，並支援完美無阻塞的 SSE / HTTP 串流文字輸出 (Streaming)。

### 專案結構導覽
請進入 `agent-platform` 目錄查看詳細的實作細節與各項模組：
- `core/orchestrator/`：基於 LangChain 的任務編排與記憶管理。
- `core/data_engine/`：基於 LlamaIndex 的高階資料處理與混合檢索工具。
- `core/cache_optimizer/`：上下文壓縮與 KV Cache 前綴對齊機制。
- `mcp_server/`：原生 Model Context Protocol 協議層。
- `platform_api/`：API 路由、Key 鑑權與多租戶服務化封裝。

---

## 🇺🇸 English Introduction

### Why Do You Need This Architecture? What Pain Points Does It Solve?

When moving from experimental AI scripts to production-ready applications, developers typically face several critical bottlenecks:
1. **Isolated Tool Ecosystems**: Most agent frameworks tightly couple their tools, making it difficult to share or plug-and-play tools across different systems.
2. **Context Window Overflow & Latency**: As conversations grow, unbounded history wastes tokens and destroys LLM Prefix Caching hit rates, causing huge latency spikes.
3. **Suboptimal Retrieval Quality**: Standard vector-only retrieval often misses exact-match keyword intents.
4. **Lack of Enterprise-Grade Management**: Simple scripts cannot handle API Key isolation, concurrency locking, or multi-tenant requirements out of the box.

### What Can OmniAgent Platform Do For You?

To solve these problems, this generic architecture provides four core capabilities:

* 🔌 **Native MCP (Model Context Protocol) Support**: The framework acts as both an MCP Server and Client. It can expose its internal capabilities (like retrieval or custom tools) to external ecosystems like Claude Desktop/Cursor, while also seamlessly digesting external MCP Servers as tools for the Agent.
* 🧠 **Hybrid RAG via Dual Engines**: We decouple orchestration from data. **LangChain acts as the brain for task orchestration**, while **LlamaIndex operates as the heavy-duty data engine**. It utilizes Vector Search + BM25, combined with RRF (Reciprocal Rank Fusion) for highly accurate knowledge retrieval.
* ⚡ **KV-Cache Aware Context Optimization**: The unique `ContextOptimizer` forces stable System Prompts and Few-shot prefixes at the application layer. This allows backend inference engines (like vLLM or SGLang) to maximize PagedAttention efficiency, significantly reducing TTFT (Time To First Token). It also seamlessly auto-compresses conversation history when approaching the budget limit.
* 🛡️ **Production-Ready API Service**: This is not just a script; it's a scalable FastAPI microservice. It features built-in API Key management, tenant/agent/session isolation, thread-safe memory locks, and true non-blocking SSE/HTTP streaming.

### Project Navigation
Navigate to the `agent-platform` directory to explore the core implementations:
- `core/orchestrator/`: LangChain-based agent routing and memory management.
- `core/data_engine/`: LlamaIndex-based data processing and hybrid retrieval.
- `core/cache_optimizer/`: Context compression and KV-Cache prefix alignment.
- `mcp_server/`: The native Model Context Protocol communication layer.
- `platform_api/`: FastAPI routes, tenant isolation, and API Key authentication.
