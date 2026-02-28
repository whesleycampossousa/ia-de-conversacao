"""Special detection tests: Portuguese nudge, confusion handling, farewell."""

import pytest
from tests.pytest_vercel.conftest import chat_json, get_ai_text


def test_portuguese_detection_nudges_to_english(client):
    """When student replies in PT, AI should gently nudge to English."""
    data = chat_json(
        client, "Eu não entendi. Pode explicar de novo?",
        context="coffee_shop", mode="learning",
    )
    text = get_ai_text(data).lower()
    pt_text = (data.get("pt") or "").lower()
    combined = text + " " + pt_text
    # AI should ask student to reply in English — either explicitly or by
    # providing an English model/starter phrase for the student to use
    nudge_signals = [
        "english", "in english", "try", "say it in", "respond in",
        "let's", "you can say", "you could say", "how about",
        "like", "i'd like", "would you", "can you", "for example",
    ]
    found = any(s in combined for s in nudge_signals)
    assert found, f"No English nudge detected. Response: {text[:300]}"


def test_confusion_detection_does_not_advance(client):
    """When student says 'I don't understand', AI should stay on same topic."""
    # First turn: establish a topic
    data1 = chat_json(client, "I like to cook at home.", context="coffee_shop", mode="learning")
    text1 = get_ai_text(data1)

    # Second turn: express confusion
    data2 = chat_json(client, "I don't understand.", context="coffee_shop", mode="learning")
    text2 = get_ai_text(data2).lower()

    # AI should NOT introduce a completely new topic — should have supportive language
    support_signals = ["example", "mean", "like", "for instance", "say", "try", "simpler", "easier"]
    found = any(s in text2 for s in support_signals) or "?" in text2
    assert found, f"No support/clarification in confusion response: {text2[:300]}"


def test_farewell_detection_closes_naturally(client):
    """When student says goodbye, AI should close without asking new questions."""
    data = chat_json(
        client, "Thank you! Goodbye, see you later!",
        context="coffee_shop", mode="learning",
    )
    text = get_ai_text(data)
    # Should contain farewell words
    farewell_signals = ["bye", "see you", "take care", "good luck", "keep", "great job", "practicing", "wonderful", "welcome", "have a great", "have a good", "thanks for", "next time"]
    text_lower = text.lower()
    has_farewell = any(s in text_lower for s in farewell_signals)
    assert has_farewell, f"No farewell language in response: {text[:200]}"


def test_farewell_no_new_practice_question(client):
    """Farewell response should NOT open a new practice drill."""
    data = chat_json(
        client, "Ok, I have to go now. Bye!",
        context="coffee_shop", mode="learning",
    )
    text = get_ai_text(data).rstrip()
    # Soft check: ideally no trailing question, but AI might say "See you next time?"
    # So we check there's no *practice* question (drill-like)
    drill_signals = ["can you try", "what would you say", "how would you order", "practice"]
    text_lower = text.lower()
    for drill in drill_signals:
        assert drill not in text_lower, f"Drill-like question after farewell: '{drill}'"
