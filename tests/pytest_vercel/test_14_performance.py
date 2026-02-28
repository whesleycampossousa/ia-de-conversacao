"""Performance tests: response time assertions for key endpoints."""

import time

import pytest
from tests.pytest_vercel.conftest import skip_if_policy_blocked


@pytest.mark.performance
@pytest.mark.parametrize("endpoint,payload,threshold_ms", [
    ("/api/chat", {
        "text": "Hello!", "context": "coffee_shop",
        "practiceMode": "learning", "lessonLang": "en",
    }, 8000),
    ("/api/free-conversation", {
        "action": "followup",
        "main_question": "What do you do on weekends?",
        "student_answer": "I play football.",
    }, 8000),
    ("/api/suggestions", {
        "aiMessage": "Would you like anything else?",
        "context": "coffee_shop", "lessonLang": "en",
    }, 8000),
    ("/api/tts", {
        "text": "Hello world.", "speed": 1.0, "lessonLang": "en",
    }, 5000),
])
def test_endpoint_response_time(client, endpoint, payload, threshold_ms):
    start = time.perf_counter()
    resp = client.post(endpoint, json=payload, timeout=max(threshold_ms / 1000 + 5, 15))
    elapsed_ms = (time.perf_counter() - start) * 1000
    skip_if_policy_blocked(resp)
    assert resp.status_code == 200, f"{endpoint} returned {resp.status_code}"
    assert elapsed_ms < threshold_ms, (
        f"{endpoint} took {elapsed_ms:.0f}ms (limit {threshold_ms}ms)"
    )


@pytest.mark.performance
def test_health_response_time(base_url):
    """Health endpoint should be fast (no AI call)."""
    import requests
    start = time.perf_counter()
    resp = requests.get(f"{base_url}/api/health", timeout=10)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert elapsed_ms < 3000, f"/api/health took {elapsed_ms:.0f}ms (limit 3000ms)"
