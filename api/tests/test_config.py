from __future__ import annotations

import os
import sys
import pytest


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
    from app.config import settings
    assert settings.MAX_UTTERANCE_BYTES == 10 * 1024 * 1024
    assert settings.SESSION_MAX_AGE_SECONDS == 7 * 24 * 3600
    assert settings.HERMES_REQUEST_TIMEOUT == 600
    assert settings.HERMES_INTER_TOKEN_TIMEOUT == 30
    assert settings.TTS_REQUEST_TIMEOUT == 45
    assert settings.IDLE_TIMEOUT == 120
