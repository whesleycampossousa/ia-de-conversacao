"""Multi-turn conversation tests: question dedup, farewell mid-convo, confusion handling.

These tests make 6-8 API calls each and are marked as slow.
"""

import time

import pytest
from tests.pytest_vercel.conftest import chat_json, get_ai_text


def _extract_trailing_question(text):
    """Extract the last sentence ending with ? from text."""
    text = text.rstrip()
    if "?" not in text:
        return ""
    # Find the last question in the text
    sentences = text.replace("!", ".").replace("\n", " ").split("?")
    if len(sentences) >= 2:
        # The last non-empty segment before the last ?
        q = sentences[-2].strip().split(".")[-1].strip()
        return q.lower()
    return ""


@pytest.mark.slow
def test_no_question_repetition_over_6_turns(client):
    """AI should not ask the same question twice across 6 turns."""
    inputs = [
        "Hello, I'd like to practice.",
        "I usually have coffee in the morning.",
        "Yes, I like cappuccino the most.",
        "I also enjoy tea sometimes.",
        "I go to a cafe near my house.",
        "It's called Cafe Brasil.",
    ]
    questions = []
    for text in inputs:
        data = chat_json(client, text, context="coffee_shop", mode="learning")
        q = _extract_trailing_question(get_ai_text(data))
        if q:
            questions.append(q)
        time.sleep(2.5)

    # Check for duplicates (allow minor variation with normalization)
    normalized = [q.strip("? ").lower() for q in questions]
    seen = set()
    for q in normalized:
        if q in seen and len(q) > 10:  # Ignore very short questions
            pytest.fail(f"Repeated question: '{q}' in {normalized}")
        seen.add(q)


@pytest.mark.slow
def test_farewell_mid_conversation(client):
    """If student says bye mid-conversation, AI should close gracefully."""
    # Build 3 normal turns
    for text in [
        "Hi! I want to practice ordering coffee.",
        "I'd like a large latte please.",
        "With oat milk, no sugar.",
    ]:
        chat_json(client, text, context="coffee_shop", mode="learning")
        time.sleep(2.5)

    # Turn 4: farewell
    data = chat_json(client, "Ok, I need to go now. Bye!", context="coffee_shop", mode="learning")
    text = get_ai_text(data)
    text_lower = text.lower()
    # Should contain farewell language
    farewell_words = ["bye", "see you", "take care", "good luck", "keep", "practice", "great"]
    has_farewell = any(w in text_lower for w in farewell_words)
    assert has_farewell, f"No farewell in mid-convo goodbye response: {text[:200]}"


@pytest.mark.slow
def test_confusion_stays_on_topic(client):
    """When student says 'I don't understand', AI should not jump to new topic."""
    # Turn 1: start a topic
    data1 = chat_json(client, "I want to order a drink.", context="coffee_shop", mode="learning")
    text1 = get_ai_text(data1).lower()
    time.sleep(2.5)

    # Turn 2: confusion
    data2 = chat_json(client, "I don't understand the question.", context="coffee_shop", mode="learning")
    text2 = get_ai_text(data2).lower()

    # The response should still be about drinks/ordering (shared context)
    context_words = ["drink", "order", "coffee", "like", "want", "would", "try", "have", "menu"]
    on_topic = any(w in text2 for w in context_words)
    has_support = any(w in text2 for w in ["mean", "example", "simpler", "let me", "other words", "say"])
    assert on_topic or has_support, (
        f"AI may have jumped topic after confusion. Response: {text2[:300]}"
    )
