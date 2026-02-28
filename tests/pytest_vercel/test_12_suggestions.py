"""Suggestions endpoint tests: format, relevance, encoding."""

import pytest
from tests.pytest_vercel.conftest import skip_if_policy_blocked


def _get_suggestions(client, ai_message, context="coffee_shop", lang="en"):
    resp = client.post("/api/suggestions", json={
        "aiMessage": ai_message,
        "context": context,
        "lessonLang": lang,
    }, timeout=15)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"suggestions returned {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    # Suggestions may be in a "suggestions" key or be the root list
    if isinstance(data, list):
        return data
    return data.get("suggestions", data.get("data", []))


def test_suggestions_returns_list(client):
    items = _get_suggestions(client, "Would you like anything else?")
    assert isinstance(items, list), f"Expected list, got {type(items)}"
    assert len(items) >= 2, f"Expected at least 2 suggestions, got {len(items)}"


def test_suggestions_items_are_non_empty(client):
    items = _get_suggestions(client, "What size would you like?")
    for i, item in enumerate(items[:4]):
        if isinstance(item, dict):
            text = item.get("en") or item.get("text") or ""
        else:
            text = str(item)
        assert text.strip(), f"Suggestion [{i}] is empty"


def test_suggestions_encoding_ok(client, validators):
    items = _get_suggestions(client, "Gostaria de mais alguma coisa?", lang="pt")
    for item in items[:4]:
        if isinstance(item, dict):
            for field in ("en", "pt", "text"):
                val = item.get(field, "")
                if val:
                    result = validators.validate_encoding(val)
                    assert result.passed, f"Mojibake in suggestion: {result.message}"
