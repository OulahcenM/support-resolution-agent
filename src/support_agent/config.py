"""Application settings loaded from environment variables and .env."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv  # add to imports (installed with pydantic-settings)
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: SecretStr
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Storage
    database_url: str = f"sqlite:///{(DATA_DIR / 'store.db').as_posix()}"
    chroma_dir: Path = DATA_DIR / "chroma"
    knowledge_base_dir: Path = DATA_DIR / "knowledge_base"
    checkpoint_db_path: Path = DATA_DIR / "checkpoints.db"

    # Business rules — single source of truth used by the agent's tools
    store_name: str = "Lumen & Co."
    return_window_days: int = 30
    auto_refund_limit: Decimal = Decimal("100.00")
    return_label_fee: Decimal = Decimal("5.95")
    lost_package_threshold_days: int = 10

    # API
    api_key: SecretStr | None = None
    cors_origins: list[str] = ["http://localhost:8501"]

    # Demo
    demo_mode: bool = False
    demo_reset_hours: float = 6.0


@lru_cache
def get_settings() -> Settings:
    # Export .env to os.environ so libraries like LangSmith can read their variables.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return Settings()
