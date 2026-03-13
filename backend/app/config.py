"""
Configuration management for the Doomsday platform backend.
All settings are read from environment variables with safe defaults.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "Doomsday Platform API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://doomsday:doomsday@localhost:5432/doomsday"

    # ── LLM ───────────────────────────────────────────────────────────────────
    # Which LLM backend to use.  Swappable via env var — keeps abstraction.
    LLM_PROVIDER: Literal["qwen", "openai_compat", "stub"] = "qwen"

    # Qwen / vLLM / Ollama compatible endpoint (OpenAI-style REST)
    LLM_BASE_URL: str = "http://localhost:8080/v1"
    LLM_MODEL_NAME: str = "Qwen/Qwen2.5-7B-Instruct"
    LLM_API_KEY: str = "not-needed-for-local"
    LLM_MAX_TOKENS: int = 1024
    LLM_TEMPERATURE: float = 0.2
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 3

    # ── News APIs ─────────────────────────────────────────────────────────────
    NEWSAPI_KEY: str = ""
    GNEWS_API_KEY: str = ""
    # Comma-separated list of providers to try in order
    NEWS_PROVIDERS: str = "newsapi,gnews,rss"
    NEWS_MAX_ARTICLES_PER_SCAN: int = 30

    # ── Doomsday Clock ────────────────────────────────────────────────────────
    # Bulletin of the Atomic Scientists baseline (2026 reference)
    CLOCK_BASELINE_SECONDS: float = 85.0
    # Hard cap on per-recalculation delta (constraint from spec)
    CLOCK_MAX_DELTA_PER_CYCLE: float = 5.0
    # Absolute bounds for any country score
    CLOCK_MIN_SCORE: float = 60.0
    CLOCK_MAX_SCORE: float = 150.0
    # Scan schedule: 4× per day → cron "0 */6 * * *"
    CLOCK_SCAN_CRON: str = "0 */6 * * *"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_GUIDE_PER_HOUR: int = 5

    # ── Redis (optional, for caching) ─────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 3600


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
