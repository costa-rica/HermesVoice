from __future__ import annotations

import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field, field_validator, model_validator


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
    HERMES_VOICE_WEB_EMAILS: str
    HERMES_VOICE_API_KEY: str
    SESSION_SECRET: str
    LOGIN_CODE_TTL_SECONDS: int = 10 * 60
    LOGIN_CODE_LENGTH: int = 6

    # Login email delivery
    HERMES_VOICE_SMTP_HOST: str = Field(
        "",
        validation_alias=AliasChoices(
            "HERMES_VOICE_SMTP_HOST",
            "SMTP_HOST",
            "EMAIL_HOST",
        ),
    )
    HERMES_VOICE_SMTP_PORT: int = Field(
        587,
        validation_alias=AliasChoices(
            "HERMES_VOICE_SMTP_PORT",
            "SMTP_PORT",
            "EMAIL_PORT",
        ),
    )
    HERMES_VOICE_SMTP_USERNAME: str = Field(
        "",
        validation_alias=AliasChoices(
            "HERMES_VOICE_SMTP_USERNAME",
            "SMTP_USERNAME",
            "EMAIL_USER",
        ),
    )
    HERMES_VOICE_SMTP_PASSWORD: str = Field(
        "",
        validation_alias=AliasChoices(
            "HERMES_VOICE_SMTP_PASSWORD",
            "SMTP_PASSWORD",
            "EMAIL_PASSWORD",
        ),
    )
    HERMES_VOICE_SMTP_FROM_EMAIL: str = Field(
        "",
        validation_alias=AliasChoices(
            "HERMES_VOICE_SMTP_FROM_EMAIL",
            "SMTP_FROM_EMAIL",
            "MAIL_FROM",
            "EMAIL_FROM",
        ),
    )
    HERMES_VOICE_SMTP_USE_TLS: bool = Field(
        True,
        validation_alias=AliasChoices("HERMES_VOICE_SMTP_USE_TLS", "SMTP_USE_TLS"),
    )

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
    HERMES_FIRST_EVENT_TIMEOUT: float = 60
    HERMES_FIRST_DELTA_TIMEOUT: float = 120
    HERMES_INTER_TOKEN_TIMEOUT: float = 120
    HERMES_PROGRESS_INTERVAL: float = 8
    MIN_UTTERANCE_BYTES: int = 50
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
