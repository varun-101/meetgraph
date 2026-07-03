"""Typed settings for meetgraph. Single source of env config (shared .env.template).

Orchestrator-owned — build agents import `settings`, never redefine env parsing.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: str = "dev"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origin: str = "http://localhost:3000"
    jwt_secret: str = "change-me-32-bytes-min"
    guest_token_ttl_minutes: int = 240

    # Postgres (app schema)
    database_url: str = "postgresql+asyncpg://meetgraph:meetgraph@localhost:5432/meetgraph"
    sync_database_url: str = "postgresql+psycopg://meetgraph:meetgraph@localhost:5432/meetgraph"

    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    livekit_webhook_key: str = "devkey"

    # Capture / STT
    recordings_dir: Path = Path("./recordings")
    stt_model: str = "small"
    stt_compute_type: str = "int8"
    stt_device: str = "cpu"

    # LLM (DeepSeek, OpenAI-compatible) — also read directly by cognee from env
    llm_provider: str = "custom"
    llm_model: str = "deepseek/deepseek-chat"
    llm_endpoint: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""

    # Embeddings
    embedding_provider: str = "fastembed"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384

    # cognee Cloud seam (D2) — empty means self-hosted library mode
    cognee_base_url: str = ""
    cognee_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
