"""Post-session report tests: structure, nota_geral, no jargon."""

import time

import pytest
from tests.pytest_vercel.conftest import TECHNICAL_JARGON, is_gemini_exhausted, skip_if_policy_blocked

# A realistic 6-turn conversation for report generation
SAMPLE_CONVERSATION = [
    {"sender": "ai", "text": "Welcome! What would you like to order today?"},
    {"sender": "user", "text": "I want a coffee big please."},
    {"sender": "ai", "text": "Sure! Would you like a big coffee or a small one?"},
    {"sender": "user", "text": "A big one. How much it costs?"},
    {"sender": "ai", "text": "A large coffee is $4.50. Would you like anything else?"},
    {"sender": "user", "text": "No, that's all. I pays with card."},
    {"sender": "ai", "text": "Sure, you can pay by card. Here you go!"},
    {"sender": "user", "text": "Thank you very much! Goodbye."},
]


@pytest.fixture(scope="module")
def report_data(client):
    """Generate a report once for the module (expensive call, retry on transient errors)."""
    last_resp = None
    for attempt in range(3):
        resp = client.post(
            "/api/report",
            json={"conversation": SAMPLE_CONVERSATION, "context": "coffee_shop"},
            timeout=50,
        )
        last_resp = resp
        skip_if_policy_blocked(resp)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("report", data)
        if is_gemini_exhausted(resp):
            time.sleep(10)
            continue
        break
    if last_resp and is_gemini_exhausted(last_resp):
        pytest.skip("Gemini RESOURCE_EXHAUSTED after 3 retries — skipped")
    assert last_resp.status_code == 200, f"Report returned {last_resp.status_code}: {last_resp.text[:300]}"


def test_report_has_required_fields(report_data):
    required = ["titulo", "nota_geral"]
    for field in required:
        assert field in report_data, (
            f"Missing '{field}' in report. Keys: {list(report_data.keys())}"
        )


def test_report_nota_geral_range(report_data):
    nota = report_data.get("nota_geral")
    assert nota is not None, "nota_geral is missing"
    assert isinstance(nota, (int, float)), f"nota_geral should be numeric, got {type(nota)}"
    assert 0 <= nota <= 100, f"nota_geral={nota} outside 0-100 range"


def test_report_correcoes_structure(report_data):
    correcoes = report_data.get("correcoes", [])
    if not correcoes:
        pytest.skip("No correcoes in report (may be valid if no errors detected)")
    for i, item in enumerate(correcoes[:5]):
        assert isinstance(item, dict), f"correcoes[{i}] should be dict, got {type(item)}"
        # Check for at least some useful fields
        has_useful = any(k in item for k in [
            "fraseOriginal", "fraseCorrigida", "ruim", "boa",
            "avaliacaoGeral", "comentarioBreve", "explicacaoDetalhada",
        ])
        assert has_useful, f"correcoes[{i}] missing useful fields. Keys: {list(item.keys())}"


def test_report_no_grammar_jargon(report_data):
    """Explanations should use everyday language, not grammar terminology."""
    correcoes = report_data.get("correcoes", [])
    for item in correcoes[:5]:
        for field in ["explicacaoDetalhada", "comentarioBreve", "explicacao"]:
            text = item.get(field, "")
            if text:
                text_lower = text.lower()
                for term in TECHNICAL_JARGON:
                    assert term not in text_lower, (
                        f"Jargon '{term}' in report explanation: {text[:200]}"
                    )
