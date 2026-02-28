#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for Qwen online TTS helpers and endpoint wiring."""

import importlib.util
from pathlib import Path
from datetime import timedelta

import pytest


def _load_api_module():
    project_root = Path(__file__).resolve().parents[1]
    api_path = project_root / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("api_index", api_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return _load_api_module()


def _build_auth_header(module, email="student@example.com"):
    token = module.jwt.encode(
        {
            "user_id": "test-user",
            "email": email,
            "is_admin": False,
            "exp": module._utc_now() + timedelta(hours=1),
        },
        module.app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_extract_qwen_audio_url(module):
    payload = {"output": {"audio": {"url": "https://example.com/audio.mp3"}}}
    assert module._extract_qwen_audio_url(payload) == "https://example.com/audio.mp3"


def test_legacy_voice_hints_are_ignored(module):
    assert module._is_legacy_voice_hint("lesson") is True
    assert module._is_legacy_voice_hint("achernar") is True
    assert module._is_legacy_voice_hint("en-US-Chirp3-HD-Achernar") is True
    assert module._is_legacy_voice_hint("qwen-tts-vc-cl16s102201655-voice-20260221005533940-cc82") is False


def test_synthesize_qwen_online_with_audio_url(module, monkeypatch):
    captured_payload = {}

    class DummyResponse:
        def __init__(self, status_code, json_body=None, content=b"", text=""):
            self.status_code = status_code
            self._json_body = json_body or {}
            self.content = content
            self.text = text

        def json(self):
            return self._json_body

    def fake_post(*_args, **kwargs):
        captured_payload.update(kwargs.get("json") or {})
        return DummyResponse(
            200,
            {"output": {"audio": {"url": "https://example.com/tts.mp3"}}},
        )

    def fake_get(*_args, **_kwargs):
        return DummyResponse(200, content=b"ID3" + b"\x00" * 256)

    monkeypatch.setattr(module, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(module, "REQUESTS_AVAILABLE", True)
    monkeypatch.setattr(module.requests, "post", fake_post)
    monkeypatch.setattr(module.requests, "get", fake_get)

    audio, err = module._synthesize_qwen_online(
        text="Hello there",
        lesson_lang="en",
        speed=1.0,
        voice_name="Clone16",
        model_name="qwen3-tts-vc-2026-01-22",
    )

    assert err == ""
    assert isinstance(audio, (bytes, bytearray))
    assert len(audio) > 100
    assert captured_payload.get("model") == "qwen3-tts-vc-2026-01-22"
    assert captured_payload.get("input", {}).get("voice") == "Clone16"
    assert "parameters" not in captured_payload


def test_tts_endpoint_prefers_qwen_online(module, monkeypatch):
    client = module.app.test_client()

    monkeypatch.setattr(module, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(module, "GOOGLE_API_KEY", "")
    monkeypatch.setattr(module, "REQUESTS_AVAILABLE", True)
    monkeypatch.setattr(module, "get_lesson_audio_cache", lambda _text: (None, None))
    monkeypatch.setattr(module, "get_audio_from_cache", lambda _path: None)
    monkeypatch.setattr(module, "save_audio_to_cache", lambda _audio, _path: True)
    monkeypatch.setattr(
        module,
        "_synthesize_qwen_online",
        lambda **_kwargs: (b"ID3" + b"\x01" * 512, ""),
    )

    response = client.post(
        "/api/tts",
        json={"text": "Testing qwen tts", "speed": 1.0, "lessonLang": "en"},
        headers=_build_auth_header(module),
    )

    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    assert "audio/" in (response.headers.get("Content-Type", "").lower())
    assert len(response.data) > 100
