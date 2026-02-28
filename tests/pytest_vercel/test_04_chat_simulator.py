"""Simulator mode behavioral tests — zero teaching, concise, in-character."""

import pytest
from tests.pytest_vercel.conftest import (
    ROBOTIC_PHRASES,
    ROBOTIC_PHRASES_SIMULATOR_ONLY,
    SIMULATOR_TEACHING_PHRASES,
    chat_json,
    get_ai_text,
)


@pytest.mark.parametrize("context", ["coffee_shop", "restaurant", "airport", "hotel"])
def test_simulator_response_under_40_words(client, context):
    data = chat_json(client, "Hi there!", context=context, mode="simulator")
    text = get_ai_text(data)
    wc = len(text.split())
    assert wc <= 45, f"Simulator response too long: {wc} words (max ~40) in {context}"


@pytest.mark.parametrize("context", ["coffee_shop", "restaurant"])
def test_simulator_no_teaching_phrases(client, context):
    data = chat_json(client, "I want a coffee big.", context=context, mode="simulator")
    text = get_ai_text(data).lower()
    for phrase in SIMULATOR_TEACHING_PHRASES:
        assert phrase not in text, f"Teaching phrase '{phrase}' found in simulator ({context})"


def test_simulator_no_robotic_phrases(client):
    data = chat_json(client, "Can I have a latte?", context="coffee_shop", mode="simulator")
    text = get_ai_text(data).lower()
    for phrase in ROBOTIC_PHRASES + ROBOTIC_PHRASES_SIMULATOR_ONLY:
        assert phrase not in text, f"Robotic phrase '{phrase}' found in simulator"


def test_simulator_recast_not_explicit_correction(client):
    """If student makes adjective order error, simulator should recast naturally."""
    data = chat_json(client, "I want a coffee big.", context="coffee_shop", mode="simulator")
    text = get_ai_text(data).lower()
    # Should NOT contain explicit correction language
    for forbidden in ["wrong", "incorrect", "mistake", "should say", "instead of"]:
        assert forbidden not in text, f"Explicit correction '{forbidden}' in simulator"


def test_simulator_stays_in_character(client):
    """Even when asked to teach, simulator should stay in service-worker role."""
    data = chat_json(
        client, "Can you teach me English?",
        context="coffee_shop", mode="simulator",
    )
    text = get_ai_text(data).lower()
    for phrase in SIMULATOR_TEACHING_PHRASES:
        assert phrase not in text, f"Broke character: '{phrase}' in response to teach request"


def test_simulator_has_feedback_field(client):
    """Simulator should return a separate feedback field (PT grammar tip)."""
    data = chat_json(client, "I has a question.", context="coffee_shop", mode="simulator")
    feedback = data.get("feedback")
    # feedback may be empty string or null if no error, but the field should exist
    assert "feedback" in data, f"Missing 'feedback' field in simulator response. Keys: {list(data.keys())}"


def test_simulator_ends_with_question_or_offer(client):
    data = chat_json(client, "I'd like a cappuccino.", context="coffee_shop", mode="simulator")
    text = get_ai_text(data).rstrip()
    # Simulator should usually end with ? or offer (soft check)
    ends_ok = text.endswith("?") or any(w in text.lower() for w in ["here you go", "anything else", "would you", "else"])
    assert ends_ok, f"Simulator response doesn't end with question/offer: ...{text[-80:]}"
