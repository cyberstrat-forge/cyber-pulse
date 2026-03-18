from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "postgresql://localhost/cyberpulse"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4

    # Dramatiq
    dramatiq_broker_url: str = "redis://localhost:6379/1"
    dramatiq_max_retries: int = 3
    dramatiq_retry_delay: int = 60

    # APScheduler
    scheduler_enabled: bool = True
    default_fetch_interval: int = 3600  # 1 hour

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/cyberpulse.log"

    # Security
    secret_key: str = "change-this-to-a-random-secret-key"
    api_token_expire_minutes: int = 1440

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()