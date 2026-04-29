from __future__ import annotations

import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator


_VALID_ENVIRONMENTS = {"development", "testing", "production"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Identity
    NAME_APP: str
    RUN_ENVIRONMENT: str
    PATH_TO_LOGS: str = ""

    # Auth
    HERMES_VOICE_WEB_PASSWORD: str
    HERMES_VOICE_API_KEY: str
    SESSION_SECRET: str

    # OpenAI
    OPENAI_API_KEY: str

    # Hermes
    HERMES_BASE_URL: str = "http://127.0.0.1:8642/v1"
    HERMES_API_KEY: str
    HERMES_MODEL: str = "hermes-agent"

    # Audio/models
    STT_MODEL: str = "whisper-1"
    TTS_MODEL: str = "tts-1"
    TTS_VOICE: str = "alloy"
    TTS_FORMAT: str = "opus"
    UPLINK_FORMAT: str = "wav"
    DOWNLINK_FORMAT: str = "opus"

    # Timeouts and limits
    HERMES_REQUEST_TIMEOUT: int = 600
    HERMES_INTER_TOKEN_TIMEOUT: int = 30
    TTS_REQUEST_TIMEOUT: int = 45
    IDLE_TIMEOUT: int = 120
    MAX_UTTERANCE_BYTES: int = 10 * 1024 * 1024
    SESSION_MAX_AGE_SECONDS: int = 7 * 24 * 3600

    @field_validator("RUN_ENVIRONMENT")
    @classmethod
    def validate_run_environment(cls, v: str) -> str:
        if v not in _VALID_ENVIRONMENTS:
            print(
                f"FATAL: RUN_ENVIRONMENT={v!r} is invalid. "
                f"Must be one of {sorted(_VALID_ENVIRONMENTS)}",
                file=sys.stderr,
            )
            sys.exit(1)
        return v

    @model_validator(mode="after")
    def validate_logs_path(self) -> "Settings":
        if self.RUN_ENVIRONMENT in ("testing", "production") and not self.PATH_TO_LOGS:
            print(
                "FATAL: PATH_TO_LOGS is required when RUN_ENVIRONMENT is "
                f"{self.RUN_ENVIRONMENT!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        return self


def load_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        print(f"FATAL: configuration error: {exc}", file=sys.stderr)
        sys.exit(1)


settings = load_settings()
