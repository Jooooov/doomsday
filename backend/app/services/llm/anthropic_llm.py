"""Anthropic/Claude provider — cloud alternative to local Qwen"""
import json
import logging
from typing import AsyncIterator
from app.services.llm.base import BaseLLM
from app.core.config import settings

logger = logging.getLogger(__name__)


class AnthropicLLM(BaseLLM):
    def __init__(self):
        import anthropic
        self.client = anthropic.AsyncAnthropic()
        self.model = "claude-sonnet-4-6"
        self.max_retries = settings.LLM_MAX_RETRIES

    async def generate(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def stream(self, prompt: str, system: str = "", max_tokens: int = 4000) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            async for chunk in s.text_stream:
                yield chunk

    async def generate_json(self, prompt: str, system: str = "", max_tokens: int = 2000) -> dict:
        for attempt in range(self.max_retries):
            try:
                text = await self.generate(prompt, system, max_tokens)
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return json.loads(text)
            except Exception as e:
                logger.warning(f"LLM JSON attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt == self.max_retries - 1:
                    raise
        raise RuntimeError("LLM JSON generation failed")
