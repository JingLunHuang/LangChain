# Agent platform

Agent-platform uses LangChain to orchestrate agents and LlamaIndex for data indexing.
Its MCP tools include ping, hybrid_retrieve and agent_invoke.
Hybrid retrieval combines vector similarity and BM25 lexical retrieval using reciprocal rank fusion.
HTTP requests use X-API-Key. Sessions are isolated by tenant, agent and session ID.
