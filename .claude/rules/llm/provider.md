# LLM Provider Rules

## Provider: Ollama (primary)
- Endpoint: `http://192.168.9.160:11434`
- Model: `gpt-oss:120b`
- Interface: OpenAI-compatible API (`/v1/chat/completions`)

## Client
- Uses `openai` Python library with custom `base_url`
- Switching provider = changing endpoint + model in YAML config
- `LLMClient` in `src/lmetl/llm/client.py`

## Future Providers
- vLLM + Ray: OpenAI-compatible, same client
- External APIs (Claude/OpenAI): deferred, architecture supports it

## Extraction Methods
- `direct_prompt`: LLM prompt (Phase 1, implemented)
- `internal_skill_api`: company internal LLM skill API (deferred)
- `langchain_skill`: self-built LangChain skill (deferred)
