# KV cache

KV cache stores attention keys and values in the inference engine.
PagedAttention manages memory blocks inside engines such as vLLM.
The application stabilizes the system prompt, examples and tool order to help prefix reuse.
It cannot directly manage GPU memory. History summaries can lose information.
