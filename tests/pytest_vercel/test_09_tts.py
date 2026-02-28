"""TTS endpoint tests: audio binary, content-type, size."""

import time

import pytest
from tests.pytest_vercel.conftest import skip_if_policy_blocked


def test_tts_returns_audio_binary(client):
    resp = client.post("/api/tts", json={"text": "Hello, how are you?", "speed": 1.0, "lessonLang": "en"}, timeout=15)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"TTS returned {resp.status_code}: {resp.text[:200]}"
    ct = resp.headers.get("Content-Type", "").lower()
    assert "audio/" in ct, f"Expected audio/* content-type, got: {ct}"
    assert len(resp.content) > 1000, f"Audio too small: {len(resp.content)} bytes"


def test_tts_valid_audio_header(client, validators):
    resp = client.post("/api/tts", json={"text": "Good morning!", "speed": 1.0, "lessonLang": "en"}, timeout=15)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200
    result = validators.validate_audio_file(resp.content)
    assert result.passed, f"Invalid audio: {result.message}"


def test_tts_portuguese_text(client):
    resp = client.post("/api/tts", json={"text": "Olá, como vai?", "speed": 1.0, "lessonLang": "pt"}, timeout=15)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"TTS PT returned {resp.status_code}"
    assert len(resp.content) > 500, "PT audio too small"


def test_tts_slow_speed(client):
    resp = client.post("/api/tts", json={"text": "Hello there!", "speed": 0.7, "lessonLang": "en"}, timeout=15)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"TTS slow-speed returned {resp.status_code}"


@pytest.mark.performance
def test_tts_response_time(client):
    start = time.perf_counter()
    resp = client.post("/api/tts", json={"text": "Testing speed.", "speed": 1.0, "lessonLang": "en"}, timeout=15)
    elapsed_ms = (time.perf_counter() - start) * 1000
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200
    assert elapsed_ms < 5000, f"TTS took {elapsed_ms:.0f}ms (limit 5000ms)"
