"""Ollama provider — Qwen3.5 on RTX 3070 Ti (local inference)"""
import json
import logging
from typing import AsyncIterator
import httpx
from app.services.llm.base import BaseLLM
from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaLLM(BaseLLM):
    def __init__(self):
        self.base_url = settings.LLM_BASE_URL
        self.model = settings.LLM_MODEL
        self.timeout = settings.LLM_TIMEOUT
        self.max_retries = settings.LLM_MAX_RETRIES

    async def generate(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def stream(self, prompt: str, system: str = "", max_tokens: int = 4000) -> AsyncIterator[str]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": messages, "stream": True},
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            chunk = data.get("message", {}).get("content", "")
                            if chunk:
                                yield chunk
                        except json.JSONDecodeError:
                            continue

    async def generate_json(self, prompt: str, system: str = "", max_tokens: int = 2000) -> dict:
        for attempt in range(self.max_retries):
            try:
                text = await self.generate(prompt, system, max_tokens)
                # Strip markdown code fences
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return json.loads(text)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"LLM JSON attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt == self.max_retries - 1:
                    raise
        raise RuntimeError("LLM JSON generation failed after max retries")
