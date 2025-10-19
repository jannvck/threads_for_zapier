from __future__ import annotations

import os
from dataclasses import dataclass, field


def _read_env(name: str, default: str | None = None) -> str | None:
    """Return configuration from environment variables or *_FILE secrets."""

    file_var = os.getenv(f"{name}_FILE")
    if file_var:
        try:
            with open(file_var, "r", encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError as exc:  # pragma: no cover - configuration error surface at boot
            raise RuntimeError(f"Failed to read configuration from {name}_FILE={file_var}") from exc

    value = os.getenv(name)
    if value is not None:
        return value

    return default


@dataclass
class Settings:
    threads_api_base_url: str = field(
        default_factory=lambda: _read_env(
            "THREADS_ZAPIER_THREADS_API_BASE_URL", "https://graph.threads.net"
        )
    )
    threads_client_id: str = field(
        default_factory=lambda: _read_env("THREADS_ZAPIER_THREADS_CLIENT_ID", "demo-client-id")
    )
    threads_client_secret: str = field(
        default_factory=lambda: _read_env(
            "THREADS_ZAPIER_THREADS_CLIENT_SECRET", "demo-client-secret"
        )
    )
    threads_redirect_uri: str = field(
        default_factory=lambda: _read_env(
            "THREADS_ZAPIER_THREADS_REDIRECT_URI", "https://example.com/oauth/callback"
        )
    )
    zapier_verification_token: str | None = field(
        default_factory=lambda: _read_env("THREADS_ZAPIER_ZAPIER_VERIFICATION_TOKEN")
    )
    request_timeout_seconds: float = field(
        default_factory=lambda: float(
            _read_env("THREADS_ZAPIER_REQUEST_TIMEOUT_SECONDS", "10.0")
        )
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
