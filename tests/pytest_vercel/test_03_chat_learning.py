"""Learning mode pedagogical quality tests."""

import pytest
from tests.pytest_vercel.conftest import (
    TECHNICAL_JARGON,
    chat_json,
    get_ai_text,
)


def test_learning_response_ends_with_question(client):
    data = chat_json(client, "Hi, I'm ready to practice.", context="coffee_shop", mode="learning")
    text = get_ai_text(data).rstrip()
    assert text.endswith("?"), f"Learning response should end with '?': ...{text[-80:]}"


def test_learning_no_grammar_jargon(client):
    data = chat_json(client, "I goed to the store yesterday.", context="coffee_shop", mode="learning")
    text = get_ai_text(data).lower()
    for term in TECHNICAL_JARGON:
        assert term not in text, f"Grammar jargon found: '{term}' in response"


def test_learning_word_count_reasonable(client):
    data = chat_json(client, "I like playing football with my friends.", context="coffee_shop", mode="learning")
    text = get_ai_text(data)
    wc = len(text.split())
    assert 5 <= wc <= 120, f"Word count {wc} outside reasonable range (5-120)"


def test_learning_correction_on_obvious_error(client):
    """An obvious grammar error should trigger some form of correction."""
    data = chat_json(client, "He have a car.", context="coffee_shop", mode="learning")
    # At least one of these should indicate correction
    must_retry = data.get("must_retry", False)
    turn_feedback = data.get("turn_feedback") or {}
    kind = turn_feedback.get("kind", "none")
    text = get_ai_text(data).lower()
    has_correction_hint = "has" in text or "instead" in text or "say" in text
    assert must_retry or kind != "none" or has_correction_hint, (
        f"No correction for 'He have a car.' — must_retry={must_retry}, kind={kind}"
    )


def test_learning_no_correction_on_correct_phrase(client):
    data = chat_json(client, "I went to the store yesterday.", context="coffee_shop", mode="learning")
    assert data.get("must_retry") is not True, (
        "must_retry should be False for correct phrase 'I went to the store yesterday.'"
    )


def test_learning_level_a1_simple_vocab(client):
    """A1 level: AI should use simple vocabulary (proxy: avg word length < 7)."""
    data = chat_json(
        client, "I am happy. I like cats.",
        context="coffee_shop", mode="learning",
        studentLevel="beginner",
    )
    text = get_ai_text(data)
    words = [w for w in text.split() if len(w) > 1]
    if words:
        avg_len = sum(len(w) for w in words) / len(words)
        assert avg_len < 7, f"Avg word length {avg_len:.1f} too high for A1 level"


def test_learning_response_has_teaching_element(client):
    """Learning mode should teach — response should contain a model phrase or question."""
    data = chat_json(client, "I wants to buy something.", context="coffee_shop", mode="learning")
    text = get_ai_text(data)
    # Should have either a correction or an instructive follow-up question
    has_question = "?" in text
    has_teaching = any(kw in text.lower() for kw in ["say", "try", "instead", "example", "like"])
    assert has_question or has_teaching, (
        f"No teaching element found in learning response: {text[:200]}"
    )
