"""LLM factory — swap model via LLM_PROVIDER env var (ollama | anthropic)"""
from functools import lru_cache
from app.services.llm.base import BaseLLM
from app.core.config import settings


@lru_cache(maxsize=1)
def get_llm() -> BaseLLM:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "ollama":
        from app.services.llm.ollama import OllamaLLM
        return OllamaLLM()
    elif provider == "anthropic":
        from app.services.llm.anthropic_llm import AnthropicLLM
        return AnthropicLLM()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Use 'ollama' or 'anthropic'.")
