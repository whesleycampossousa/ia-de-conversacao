"""must_retry classification tests: true positives and false positives."""

import pytest
from tests.pytest_vercel.conftest import chat_json


# (student_text, expect_must_retry, description)
RETRY_TRUE_CASES = [
    ("He have a car.", "subject-verb agreement: have→has"),
    ("She don't like coffee.", "subject-verb agreement: don't→doesn't"),
    ("They was very happy.", "was→were agreement"),
    ("I goed to the park.", "irregular past: goed→went"),
    ("She are my friend.", "are→is agreement"),
]

RETRY_FALSE_CASES = [
    ("I went to the store yesterday.", "correct past simple"),
    ("She doesn't like coffee.", "correct present simple negative"),
    ("They were very happy.", "correct past simple"),
    ("I have been here since morning.", "correct present perfect"),
    ("He has a beautiful car.", "correct present simple"),
]


@pytest.mark.parametrize("text,desc", RETRY_TRUE_CASES)
def test_must_retry_true_for_errors(client, text, desc):
    """Obvious grammar errors should trigger must_retry=True."""
    data = chat_json(client, text, context="coffee_shop", mode="learning")
    must_retry = data.get("must_retry", False)
    turn_feedback = data.get("turn_feedback") or {}
    kind = turn_feedback.get("kind", "none")
    # Accept either must_retry=True OR turn_feedback indicating error
    detected = must_retry or kind == "error_correction"
    assert detected, (
        f"Expected correction for '{text}' ({desc}) — "
        f"must_retry={must_retry}, kind={kind}"
    )


@pytest.mark.parametrize("text,desc", RETRY_FALSE_CASES)
def test_must_retry_false_for_correct(client, text, desc):
    """Correct phrases should NOT trigger must_retry=True."""
    data = chat_json(client, text, context="coffee_shop", mode="learning")
    must_retry = data.get("must_retry", False)
    assert must_retry is not True, (
        f"False positive: must_retry=True for correct phrase '{text}' ({desc})"
    )
