"""
Pytest fixtures for the Vercel production test suite.

Reuses:
  - monitor/utils/api_client.py  → APIClient (session, auth, retries)
  - monitor/utils/validators.py  → Validators (encoding, audio, behavioral)
  - tests/test_comprehensive.py  → TECHNICAL_JARGON, GRAMMAR_TOPIC_KEYWORDS, etc.
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest
import requests

# ---------------------------------------------------------------------------
# Path setup: ensure project root importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from monitor.utils.api_client import APIClient
from monitor.utils.validators import Validators

# Import validation constants from the standalone comprehensive suite
from tests.test_comprehensive import (
    GRAMMAR_TOPIC_KEYWORDS,
    ROBOTIC_PHRASES,
    ROBOTIC_PHRASES_SIMULATOR_ONLY,
    SIMULATOR_TEACHING_PHRASES,
    TECHNICAL_JARGON,
)

# ---------------------------------------------------------------------------
# Policy-429 detection helpers
# ---------------------------------------------------------------------------
POLICY_429_HINTS = (
    "weekend",
    "only available on",
    "see you next saturday",
    "practice is available",
    "limit",
)


def is_policy_429(resp):
    """True when the server returns a weekend/usage-policy 429."""
    if resp.status_code != 429:
        return False
    body = resp.text.lower()
    return any(h in body for h in POLICY_429_HINTS)


def is_gemini_exhausted(resp):
    """True when Gemini returns 429 RESOURCE_EXHAUSTED via our 500 wrapper."""
    if resp.status_code != 500:
        return False
    body = resp.text.lower()
    return "resource_exhausted" in body or "resource exhausted" in body


def skip_if_policy_blocked(resp):
    """Call inside a test: pytest.skip() when a policy block or Gemini quota is hit."""
    if is_policy_429(resp):
        pytest.skip("Weekend/usage-policy 429 — skipped, not failed")
    if is_gemini_exhausted(resp):
        pytest.skip("Gemini RESOURCE_EXHAUSTED — transient rate limit, skipped")


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def base_url():
    """Production Vercel URL (overridable via TEST_API_URL env var)."""
    override = os.environ.get("TEST_API_URL")
    if override:
        return override.rstrip("/")

    config_path = PROJECT_ROOT / "monitor" / "config" / "deployment_urls.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for env in config["environments"]:
        if env.get("enabled"):
            return env["url"].rstrip("/")
    raise RuntimeError("No enabled environment in deployment_urls.json")


@pytest.fixture(scope="session")
def auth_email():
    config_path = PROJECT_ROOT / "monitor" / "config" / "deployment_urls.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return config["auth"]["email"]


@pytest.fixture(scope="session")
def auth_password():
    return os.environ.get("MONITOR_PASSWORD", "")


@pytest.fixture(scope="session")
def client(base_url, auth_email, auth_password):
    """Authenticated APIClient — one login per test run.

    The APIClient.login() tries with password first, then falls back to
    passwordless login if the server returns 401 for admin password.
    """
    c = APIClient(base_url=base_url, email=auth_email, password=auth_password, timeout=35)
    ok = c.login()
    assert ok, f"Login failed for {auth_email} at {base_url}"
    return c


@pytest.fixture(scope="session")
def validators():
    return Validators()


# ---------------------------------------------------------------------------
# Rate-limit auto-pause (runs after every test)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _rate_limit_pause():
    yield
    time.sleep(3.5)


# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: multi-turn tests (>10 API calls)")
    config.addinivalue_line("markers", "performance: response-time assertions")


# ---------------------------------------------------------------------------
# Chat helper (used by multiple modules)
# ---------------------------------------------------------------------------
def chat(client, text, context="coffee_shop", mode="learning", lang="en", **extra):
    """Send a /api/chat request and return the raw requests.Response."""
    payload = {
        "text": text,
        "context": context,
        "practiceMode": mode,
        "lessonLang": lang,
        **extra,
    }
    return client.post("/api/chat", json=payload, timeout=30)


def chat_json(client, text, **kw):
    """Convenience: chat() + skip_if_policy_blocked + parse JSON."""
    resp = chat(client, text, **kw)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"chat returned {resp.status_code}: {resp.text[:300]}"
    return resp.json()


def get_ai_text(data):
    """Extract the main AI text from a chat response dict."""
    return data.get("text") or data.get("en") or ""
