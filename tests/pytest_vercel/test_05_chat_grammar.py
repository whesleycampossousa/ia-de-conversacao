"""Grammar topic tests: on-topic, no jargon, no fill-in-the-blank."""

import pytest
from tests.pytest_vercel.conftest import (
    GRAMMAR_TOPIC_KEYWORDS,
    TECHNICAL_JARGON,
    chat_json,
    get_ai_text,
)


@pytest.mark.parametrize("topic,student_input", [
    ("verb_to_be", "I is happy today."),
    ("present_simple", "She go to school every day."),
    ("past_simple", "Yesterday I go to the store."),
    ("present_perfect", "I have went to Paris."),
    ("conditionals_zero_first", "If it rain, I stay home."),
])
def test_grammar_response_on_topic(client, topic, student_input):
    """Response must contain at least 1 keyword for the grammar topic."""
    data = chat_json(client, student_input, context=topic, mode="learning")
    text = get_ai_text(data).lower()
    keywords = GRAMMAR_TOPIC_KEYWORDS.get(topic, [])
    if not keywords:
        pytest.skip(f"No keywords defined for topic '{topic}'")
    found = [k for k in keywords if k.lower() in text]
    assert found, (
        f"No keywords for '{topic}' in response. "
        f"Expected any of: {keywords[:8]}. Got: {text[:200]}"
    )


@pytest.mark.parametrize("topic", [
    "verb_to_be", "present_simple", "past_simple", "present_perfect",
])
def test_grammar_no_technical_jargon(client, topic):
    data = chat_json(client, "Hello, I want to practice.", context=topic, mode="learning")
    text = get_ai_text(data).lower()
    for term in TECHNICAL_JARGON:
        assert term not in text, f"Jargon '{term}' in grammar topic '{topic}'"


@pytest.mark.parametrize("topic", ["present_simple", "past_simple"])
def test_grammar_no_fill_in_blank(client, topic):
    data = chat_json(client, "I like to study English.", context=topic, mode="learning")
    text = get_ai_text(data)
    assert "___" not in text, "Fill-in-the-blank drill detected"
    assert "fill in" not in text.lower(), "Fill-in instruction detected"
    assert "complete:" not in text.lower(), "Complete-the-sentence drill detected"


def test_grammar_ends_with_question(client):
    """Grammar responses should end with a practice question."""
    data = chat_json(client, "She are my friend.", context="verb_to_be", mode="learning")
    text = get_ai_text(data).rstrip()
    assert text.endswith("?"), f"Grammar response should end with '?': ...{text[-80:]}"


def test_grammar_response_not_too_long(client):
    data = chat_json(client, "They is very tired today.", context="verb_to_be", mode="learning")
    text = get_ai_text(data)
    wc = len(text.split())
    assert wc <= 80, f"Grammar response too long: {wc} words (max ~60-80)"
