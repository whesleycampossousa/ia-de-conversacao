"""Free conversation endpoint tests: no corrections, natural flow."""

import pytest
from tests.pytest_vercel.conftest import skip_if_policy_blocked


def _free_conv(client, payload):
    resp = client.post("/api/free-conversation", json=payload, timeout=30)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"free-conversation returned {resp.status_code}: {resp.text[:300]}"
    return resp.json()


def test_free_conversation_followup_returns_text(client):
    data = _free_conv(client, {
        "action": "followup",
        "main_question": "What do you like to do on weekends?",
        "student_answer": "I play football with my friends.",
    })
    text = data.get("text", "")
    assert text, "followup returned empty text"


def test_free_conversation_followup_ends_with_question(client):
    data = _free_conv(client, {
        "action": "followup",
        "main_question": "What's your favorite food?",
        "student_answer": "I like pizza a lot.",
    })
    text = data.get("text", "").rstrip()
    assert text.endswith("?"), f"followup should end with '?': ...{text[-80:]}"


def test_free_conversation_opinion_returns_text(client):
    data = _free_conv(client, {
        "action": "opinion",
        "main_question": "What's your favorite movie?",
        "student_answer": "I like action movies.",
        "followup_question": "Which one is your favorite?",
        "followup_answer": "I love The Matrix.",
    })
    text = data.get("text", "")
    assert text, "opinion returned empty text"


def test_free_conversation_no_corrections_on_errors(client):
    """Free conversation mode should NEVER correct grammar."""
    data = _free_conv(client, {
        "action": "followup",
        "main_question": "Tell me about your daily routine.",
        "student_answer": "I goes to work every day and I eats lunch at 12.",
    })
    text = data.get("text", "").lower()
    correction_signals = ["should say", "instead of", "wrong", "mistake", "incorrect", "correct form"]
    for signal in correction_signals:
        assert signal not in text, (
            f"Grammar correction '{signal}' found in free conversation mode"
        )


def test_free_conversation_transition_returns_text(client):
    data = _free_conv(client, {
        "action": "transition",
        "main_question": "What do you do for fun?",
        "student_answer": "I play video games.",
        "followup_question": "What games do you play?",
        "followup_answer": "I play FIFA and Minecraft.",
        "previous_transitions": [],
    })
    text = data.get("text", "")
    assert text, "transition returned empty text"
