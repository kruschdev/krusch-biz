"""
src/backend/config.py
=====================
Centralized configuration and sovereign air-gap security boundaries for KruschBiz.
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration for KruschBiz backend."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = os.getenv("APP_ENV", "development")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    ALLOW_LAN: bool = os.getenv("ALLOW_LAN", "0") in ("1", "true", "True")

    # Database (Port 5436 to avoid conflict with KruschLaw 5435 and default 5432)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://kruschbiz:kruschbiz_secret@localhost:5436/kruschbiz_db"
    )

    # Ollama Endpoints
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_EMBED_HOST: str = os.getenv("OLLAMA_EMBED_HOST", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))

    # Models
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "bge-large")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", os.getenv("OLLAMA_EMBED_MODEL", "bge-large"))
    OLLAMA_LLM_MODEL: str = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5-coder:7b")
    TAGGER_MODEL: str = os.getenv("TAGGER_MODEL", "qwen2.5-coder:7b")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    USE_MOCK_EMBEDDINGS: bool = os.getenv("USE_MOCK_EMBEDDINGS", "0") in ("1", "true", "True")
    HEADLESS_MODE: bool = os.getenv("HEADLESS_MODE", "0") in ("1", "true", "True")

    # Ports
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8086"))
    FRONTEND_PORT: int = int(os.getenv("FRONTEND_PORT", "8506"))
    DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", "5436"))

    # Timeouts & Limits
    EMBED_TIMEOUT: float = float(os.getenv("EMBED_TIMEOUT", "30.0"))
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "120.0"))
    TAGGER_TIMEOUT: float = float(os.getenv("TAGGER_TIMEOUT", "15.0"))
    DEFAULT_RETRIEVAL_LIMIT: int = int(os.getenv("DEFAULT_RETRIEVAL_LIMIT", "5"))
    MAX_INGEST_CHUNKS_PER_DOC: int = int(os.getenv("MAX_INGEST_CHUNKS_PER_DOC", "1000"))

    # Batching & Performance
    EMBED_BATCH_SIZE: int = int(os.getenv("EMBED_BATCH_SIZE", "16"))

    # Security & Air-Gap Boundaries
    API_KEY: str | None = os.getenv("API_KEY", None)
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:8506,http://127.0.0.1:8506,http://localhost:3000,http://127.0.0.1:3000"
    )
    ALLOWED_INGEST_DIRS: str = os.getenv(
        "ALLOWED_INGEST_DIRS",
        "/app/data,/app/data/ingest"
    )
    KRUSCH_NEXUS_PATH: str | None = os.getenv("KRUSCH_NEXUS_PATH", None)

    extra_allowed_dirs: list[str] = []

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_ingest_dirs_list(self) -> list[str]:
        dirs = [os.path.abspath(d.strip()) for d in self.ALLOWED_INGEST_DIRS.split(",") if d.strip()]
        local_data = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"))
        if local_data not in dirs:
            dirs.append(local_data)
            dirs.append(os.path.join(local_data, "ingest"))
            dirs.append(os.path.join(local_data, "fixtures"))
        for extra in self.extra_allowed_dirs:
            dirs.append(os.path.abspath(extra.strip()))
        return dirs

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


def is_loopback_or_private_host(url_or_host: str) -> bool:
    """Inspect whether a configured host/URL resides strictly on loopback or private networks."""
    import ipaddress
    import urllib.parse
    if not url_or_host:
        return False
    try:
        if "://" in url_or_host:
            hostname = urllib.parse.urlparse(url_or_host).hostname or ""
        else:
            hostname = url_or_host

        hostname = hostname.strip().lower()
        if (
            hostname in ("localhost", "127.0.0.1", "::1", "host.docker.internal", "db", "backend", "frontend")
            or hostname.startswith("mock-")
            or hostname.endswith(".local")
            or hostname.endswith(".internal")
        ):
            return True
        ip = ipaddress.ip_address(hostname)
        return ip.is_loopback or ip.is_private
    except Exception:
        return False


def validate_security_invariants(s: Settings) -> None:
    """Enforce API key requirement outside development, loopback binding, and loopback Ollama hosts unless ALLOW_LAN is set."""
    # Invariant: Disallow empty, whitespace, or default placeholder API keys outside development
    disallowed_keys = ("", "default", "changeme", "secret", "kruschbiz_secret", "replace_me")
    if s.APP_ENV != "development" and (not s.API_KEY or not s.API_KEY.strip() or s.API_KEY.strip().lower() in disallowed_keys):
        raise RuntimeError(
            "Security Violation: A non-default API_KEY is strictly required outside development environment (APP_ENV != 'development')."
        )
    if (s.HOST == "0.0.0.0" or not is_loopback_or_private_host(s.HOST)) and not s.ALLOW_LAN:
        raise RuntimeError(
            f"Security Violation: Refusing to bind to non-loopback host '{s.HOST}' without ALLOW_LAN=1."
        )
    if not is_loopback_or_private_host(s.OLLAMA_BASE_URL) and not s.ALLOW_LAN:
        raise RuntimeError(
            f"Security Violation: Refusing connection to non-local Ollama LLM host '{s.OLLAMA_BASE_URL}' without ALLOW_LAN=1."
        )
    if not is_loopback_or_private_host(s.OLLAMA_EMBED_HOST) and not s.ALLOW_LAN:
        raise RuntimeError(
            f"Security Violation: Refusing connection to non-local Ollama embedding host '{s.OLLAMA_EMBED_HOST}' without ALLOW_LAN=1."
        )


settings = Settings()
