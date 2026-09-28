# OmniAgent / OmniRoute platform

OmniRoute classifies general, coding, reasoning, writing and knowledge tasks before selecting a model.
Operator-declared capabilities, cost and latency tiers, tool support and input capacity guide selection.
These settings are routing policy, not measured model rankings.
Users can override one request or pin a model to a session and later return to automatic routing.
Switching models preserves conversation history and reuses the tenant's retrieval index.
LangChain executes the selected Agent; LlamaIndex provides vector and BM25 retrieval with reciprocal rank fusion.
Retrieval returns source excerpts, and the selected Agent model writes the answer.
The seven MCP tools are ping, hybrid_retrieve, model_catalog, route_preview, model_switch, agent_invoke and routing_traces.
API requests use X-API-Key; API sessions are isolated by tenant, agent and session ID.
MCP is operator scoped with a separate network access key.
