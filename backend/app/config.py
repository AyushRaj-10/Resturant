from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory for locating the .env file from root or backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application configuration loaded from environment or .env file."""

    # Database Configuration
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "restaurant_oms"

    # Application Environment
    APP_ENV: str = "development"

    # LLM Configuration (Optional)
    LLM_PROVIDER: Literal["none", "groq"] = "none"
    LLM_API_KEY: str = ""
    LLM_MODEL: Optional[str] = ""
    LLM_TIMEOUT_SECONDS: int = 15
    LLM_MAX_TOKENS: int = 400
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_RETRIES: int = 1

    # Multi-Agent Configuration
    AGENT_MAX_STEPS: int = 5
    AGENT_MAX_TOOL_CALLS: int = 6
    AGENT_TIMEOUT_SECONDS: float = 30.0
    AGENT_MAX_HISTORY_TURNS: int = 6

    # Guardrail and Confirmation Policy Settings (Step 11)
    AGENT_WRITES_ENABLED: bool = True
    AGENT_DESTRUCTIVE_ENABLED: bool = True
    AGENT_CONFIRM_TTL_SECONDS: int = 120
    AGENT_MAX_DESTRUCTIVE_PER_REQUEST: int = 1
    AGENT_MAX_WRITES_PER_REQUEST: int = 3
    AGENT_MAX_TOOL_CALLS_PER_MINUTE_PER_SESSION: int = 20
    AGENT_MAX_DISCOUNT_PERCENT: float = 20.0
    AGENT_MAX_ORDER_TOTAL: float = 20000.0

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """Construct SQLAlchemy MySQL database URL using PyMySQL driver."""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached instance of application settings."""
    return Settings()
