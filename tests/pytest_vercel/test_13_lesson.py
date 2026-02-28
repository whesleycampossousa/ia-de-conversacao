"""Structured lesson endpoint tests: start, show_options, evaluate."""

import pytest
from tests.pytest_vercel.conftest import skip_if_policy_blocked


def _lesson(client, payload):
    resp = client.post("/api/lesson", json=payload, timeout=20)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"lesson returned {resp.status_code}: {resp.text[:300]}"
    return resp.json()


def test_lesson_start(client):
    data = _lesson(client, {"context": "coffee_shop", "action": "start"})
    # Should have some text content for the welcome
    has_text = data.get("text") or data.get("message") or data.get("welcome")
    assert has_text, f"Lesson start returned no text. Keys: {list(data.keys())}"


def test_lesson_show_options(client):
    data = _lesson(client, {"context": "coffee_shop", "action": "show_options", "layer": 1})
    # Should have options or text describing options
    has_content = data.get("options") or data.get("text") or data.get("message")
    assert has_content, f"show_options returned no content. Keys: {list(data.keys())}"


def test_lesson_evaluate_practice(client):
    data = _lesson(client, {
        "context": "coffee_shop",
        "action": "evaluate_practice",
        "text": "Can I have a coffee, please?",
        "layer": 1,
    })
    # Should have evaluation result
    has_result = data.get("result") or data.get("text") or data.get("evaluation") or data.get("status")
    assert has_result, f"evaluate_practice returned no result. Keys: {list(data.keys())}"


def test_lesson_select_option(client):
    """select_option should return the practice prompt for the chosen option."""
    data = _lesson(client, {
        "context": "coffee_shop",
        "action": "select_option",
        "layer": 0,
        "option": 0,
    })
    has_content = data.get("text") or data.get("selected_phrase") or data.get("practice_prompt")
    assert has_content, f"select_option returned no content. Keys: {list(data.keys())}"
