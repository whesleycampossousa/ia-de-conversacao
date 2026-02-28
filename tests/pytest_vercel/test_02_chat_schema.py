"""Chat endpoint JSON schema validation across modes and contexts."""

import pytest
from tests.pytest_vercel.conftest import chat, skip_if_policy_blocked, get_ai_text


@pytest.mark.parametrize("mode,context", [
    ("learning", "coffee_shop"),
    ("learning", "job_interview"),
    ("simulator", "restaurant"),
    ("simulator", "airport"),
])
def test_chat_returns_200_with_text(client, mode, context):
    resp = chat(client, "Hello, how are you?", context=context, mode=mode)
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"Status {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    ai_text = get_ai_text(data)
    assert ai_text, f"Empty AI text. Keys: {list(data.keys())}"


@pytest.mark.parametrize("mode,context", [
    ("learning", "coffee_shop"),
    ("simulator", "restaurant"),
])
def test_chat_must_retry_is_bool(client, mode, context):
    resp = chat(client, "I like coffee.", context=context, mode=mode)
    skip_if_policy_blocked(resp)
    data = resp.json()
    mr = data.get("must_retry")
    assert isinstance(mr, bool), f"must_retry should be bool, got {type(mr).__name__}: {mr}"


def test_chat_suggested_words_is_list(client):
    resp = chat(client, "I want a coffee please.", context="coffee_shop", mode="learning")
    skip_if_policy_blocked(resp)
    data = resp.json()
    sw = data.get("suggested_words")
    assert sw is None or isinstance(sw, list), f"suggested_words should be list or null, got {type(sw)}"


def test_chat_encoding_no_mojibake(client, validators):
    resp = chat(client, "Olá, estou praticando.", context="coffee_shop", mode="learning")
    skip_if_policy_blocked(resp)
    data = resp.json()
    for field in ("text", "en", "pt", "translation"):
        val = data.get(field)
        if isinstance(val, str) and val:
            result = validators.validate_encoding(val)
            assert result.passed, f"Mojibake in '{field}': {result.message}"


def test_chat_translation_differs_from_en(client):
    resp = chat(client, "I like to play soccer.", context="coffee_shop", mode="learning")
    skip_if_policy_blocked(resp)
    data = resp.json()
    en = data.get("text") or data.get("en") or ""
    pt = data.get("pt") or data.get("translation") or ""
    if en and pt:
        assert en.strip() != pt.strip(), "EN and PT texts are identical"
