from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Default secret key for development only - MUST be changed in production
DEFAULT_SECRET_KEY = "change-this-to-a-random-secret-key"


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

    # Ingestion
    max_consecutive_failures: int = 5  # Freeze source after this many failures

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/cyberpulse.log"

    # Security
    secret_key: str = DEFAULT_SECRET_KEY
    api_token_expire_minutes: int = 1440

    # Environment
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def validate_security_settings(self) -> None:
        """Validate security settings on startup.

        Raises:
            RuntimeError: If security settings are insecure in production
        """
        is_production = self.environment.lower() in ("production", "prod")

        if is_production and self.secret_key == DEFAULT_SECRET_KEY:
            raise RuntimeError(
                "SECURITY ERROR: secret_key is set to the default value in production! "
                "Please set SECRET_KEY environment variable to a secure random string. "
                "You can generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

        if is_production:
            logger.info("Security validation passed for production environment")


settings = Settings()

# Validate security settings on startup (only in production)
settings.validate_security_settings()