#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Security regression tests for /api/auth/login error handling."""

import importlib.util
from pathlib import Path

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


def test_login_rejects_non_json_payload_without_trace(module):
    client = module.app.test_client()
    response = client.post(
        "/api/auth/login",
        data="not-json",
        content_type="text/plain",
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload == {"error": "Invalid JSON payload"}
    assert "trace" not in payload
    assert "details" not in payload


def test_login_internal_error_hides_trace(module, monkeypatch):
    client = module.app.test_client()

    monkeypatch.setattr(module, "is_email_authorized", lambda _email: True)

    def _raise_encode(*_args, **_kwargs):
        raise RuntimeError("should-not-leak")

    monkeypatch.setattr(module.jwt, "encode", _raise_encode)

    response = client.post(
        "/api/auth/login",
        json={"email": "student@example.com", "password": ""},
    )

    assert response.status_code == 500
    payload = response.get_json()
    assert payload == {"error": "Internal server error"}
    assert "trace" not in payload
    assert "details" not in payload
