from __future__ import annotations

import pytest


def _settings_kwargs() -> dict[str, str]:
    return {
        "NAME_APP": "hermes_voice_api_test",
        "RUN_ENVIRONMENT": "development",
        "HERMES_VOICE_WEB_PASSWORD": "test-password",
        "HERMES_VOICE_API_KEY": "test-api-key",
        "SESSION_SECRET": "test-session-secret-at-least-32-chars-long",
        "OPENAI_API_KEY": "sk-test-placeholder",
        "HERMES_API_KEY": "test",
    }


def test_settings_load_successfully():
    from app.config import settings
    assert settings.NAME_APP == "hermes_voice_api_test"
    assert settings.RUN_ENVIRONMENT == "development"
    assert settings.HERMES_API_KEY == "test"


def test_settings_has_required_fields():
    from app.config import settings
    assert settings.HERMES_VOICE_WEB_PASSWORD
    assert settings.SESSION_SECRET
    assert settings.OPENAI_API_KEY
    assert settings.HERMES_BASE_URL
    assert settings.TTS_MODEL
    assert settings.STT_MODEL


def test_settings_defaults():
    from app.config import Settings

    settings = Settings(_env_file=None, **_settings_kwargs())
    assert settings.MAX_UTTERANCE_BYTES == 10 * 1024 * 1024
    assert settings.SESSION_MAX_AGE_SECONDS == 7 * 24 * 3600
    assert settings.HERMES_REQUEST_TIMEOUT == 600
    assert settings.HERMES_FIRST_EVENT_TIMEOUT == 60
    assert settings.HERMES_FIRST_DELTA_TIMEOUT == 120
    assert settings.HERMES_INTER_TOKEN_TIMEOUT == 120
    assert settings.HERMES_PROGRESS_INTERVAL == 8
    assert settings.MIN_UTTERANCE_BYTES == 50
    assert settings.TTS_REQUEST_TIMEOUT == 45
    assert settings.IDLE_TIMEOUT == 120


def test_timeout_env_overrides(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("HERMES_FIRST_EVENT_TIMEOUT", "11")
    monkeypatch.setenv("HERMES_FIRST_DELTA_TIMEOUT", "22")
    monkeypatch.setenv("HERMES_INTER_TOKEN_TIMEOUT", "33")
    monkeypatch.setenv("HERMES_PROGRESS_INTERVAL", "4.5")
    monkeypatch.setenv("MIN_UTTERANCE_BYTES", "66")

    settings = Settings(_env_file=None, **_settings_kwargs())
    assert settings.HERMES_FIRST_EVENT_TIMEOUT == 11
    assert settings.HERMES_FIRST_DELTA_TIMEOUT == 22
    assert settings.HERMES_INTER_TOKEN_TIMEOUT == 33
    assert settings.HERMES_PROGRESS_INTERVAL == 4.5
    assert settings.MIN_UTTERANCE_BYTES == 66
