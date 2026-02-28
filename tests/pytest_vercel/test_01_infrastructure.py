"""Infrastructure tests: health, scenarios, grammar-topics (no auth required)."""

import requests
import pytest


def test_health_returns_200(base_url):
    resp = requests.get(f"{base_url}/api/health", timeout=10)
    assert resp.status_code == 200


def test_health_has_status_field(base_url):
    data = requests.get(f"{base_url}/api/health", timeout=10).json()
    assert "status" in data, f"Missing 'status' field. Keys: {list(data.keys())}"


def test_health_google_api_configured(base_url):
    data = requests.get(f"{base_url}/api/health", timeout=10).json()
    assert data.get("google_api_configured") is True, "Google API not configured"


def test_scenarios_returns_list(base_url):
    resp = requests.get(f"{base_url}/api/scenarios", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}"
    assert len(data) > 0, "No scenarios returned"


def test_scenarios_items_have_id_and_title(base_url):
    items = requests.get(f"{base_url}/api/scenarios", timeout=10).json()
    for item in items[:5]:
        assert "id" in item, f"Scenario missing 'id': {item}"
        assert "title" in item, f"Scenario missing 'title': {item}"


def test_grammar_topics_returns_list(base_url):
    resp = requests.get(f"{base_url}/api/grammar-topics", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 30, f"Expected 30+ grammar topics, got {len(data)}"


def test_grammar_topics_items_have_id_and_title(base_url):
    items = requests.get(f"{base_url}/api/grammar-topics", timeout=10).json()
    for item in items[:5]:
        assert "id" in item, f"Grammar topic missing 'id': {item}"
        assert "title" in item, f"Grammar topic missing 'title': {item}"
