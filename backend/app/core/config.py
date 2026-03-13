from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://doomsday:changeme@localhost:5432/doomsday"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Auth
    SECRET_KEY: str = "change-this-to-a-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # LLM (model-agnostic)
    LLM_PROVIDER: str = "ollama"
    LLM_MODEL: str = "qwen3.5:35b-a3b"
    LLM_BASE_URL: str = "http://host.docker.internal:11434"
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT: int = 120

    # News
    NEWS_API_KEY: str = ""
    GDELT_ENABLED: bool = True

    # IP Geolocation
    IPAPI_URL: str = "http://ip-api.com/json"

    # Cloudflare
    CF_ACCOUNT_ID: str = ""
    CF_API_TOKEN: str = ""
    CF_PAGES_PROJECT: str = "doomsday-fallback"

    # Rate limiting
    GUIDE_RATE_LIMIT_PER_HOUR: int = 5
    GUIDE_RATE_LIMIT_WINDOW: int = 3600

    # Doomsday Clock
    CLOCK_SCAN_INTERVAL_HOURS: int = 6
    CLOCK_ANCHOR_SECONDS: float = 85.0
    CLOCK_MAX_DELTA_PER_SCAN: float = 5.0
    RELATIONS_UPDATE_INTERVAL_HOURS: int = 24

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Data paths
    DATA_DIR: str = "/data"
    REGIONS_DIR: str = "/data/regions"
    COUNTRIES_DIR: str = "/data/countries"
    I18N_DIR: str = "/data/i18n"


settings = Settings()
