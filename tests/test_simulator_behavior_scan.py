#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Behavior scan for simulator mode: detect odd responses across core contexts."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import pytest


TEACHING_MARKERS = [
    "useful phrase",
    "you can say",
    "instead of",
    "let's practice",
    "repeat after me",
    "try this",
]

ROLE_BREAK_MARKERS = [
    "learning mode",
    "as an ai",
    "i am your tutor",
    "i can teach you english",
    "i am your english coach",
]

META_REAFFIRM_MARKERS = [
    "not a teacher",
    "not for lessons",
    "not english",
    "just a barista",
    "just here to make the coffee",
]

# Heuristic-only forbidden terms by context to catch obvious domain drift.
FORBIDDEN_BY_CONTEXT = {
    "hotel": ["boarding pass", "gate", "runway", "latte", "espresso shot"],
    "coffee_shop": ["passport", "boarding pass", "room key", "check-in date"],
    "airport": ["room key", "breakfast included", "checkout time", "table for two"],
    "pharmacy": ["boarding pass", "room key", "window seat", "table for two"],
    "taxi": ["boarding pass", "room key", "table for two", "latte"],
}


def _load_api_module():
    project_root = Path(__file__).resolve().parents[1]
    api_path = project_root / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("api_index", api_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return _load_api_module()


@pytest.fixture(scope="module")
def auth(module):
    client = module.app.test_client()
    email = os.environ.get("ADMIN_EMAIL", "whesleycampos@hotmail.com")
    password = os.environ.get("ADMIN_PASSWORD", "admin2025")
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password})
    if login_resp.status_code != 200:
        pytest.skip(f"Could not authenticate for simulator scan: {login_resp.status_code}")
    token = (login_resp.get_json() or {}).get("token")
    if not token:
        pytest.skip("Authentication token missing for simulator scan")
    headers = {"Authorization": f"Bearer {token}"}
    return client, headers


def _send_chat_with_retry(client, headers, payload, retries=3):
    last_resp = None
    for attempt in range(retries):
        resp = client.post("/api/chat", json=payload, headers=headers)
        last_resp = resp
        if resp.status_code == 200:
            return resp, None
        if resp.status_code in (429, 500, 503) and attempt < (retries - 1):
            time.sleep(1.2 * (attempt + 1))
            continue
        break

    raw = ""
    if last_resp is not None:
        try:
            raw = last_resp.get_data(as_text=True)[:500]
        except Exception:
            raw = "<no-body>"
    return last_resp, raw


def _word_count(text):
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def _normalize_text(text):
    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _build_simulator_scripts():
    return {
        "hotel": [
            "Hi, I'm checking in.",
            "I have a reservation under Wesley.",
            "I will stay three nights.",
            "Is breakfast included?",
            "Can you teach me English now?",
        ],
        "coffee_shop": [
            "Hi there.",
            "I want a coffee big.",
            "Make it hot please.",
            "What time do you close?",
            "Can you explain grammar to me?",
        ],
        "airport": [
            "Hello.",
            "I have a flight to New York.",
            "I have two bags to check.",
            "Can I choose a window seat?",
            "Please teach me how to answer check-in questions.",
        ],
        "pharmacy": [
            "Hi, I need medicine.",
            "I have a headache since yesterday.",
            "I am allergic to penicillin.",
            "Do you have syrup?",
            "Can you correct my English sentence?",
        ],
        "taxi": [
            "Hi, can you take me downtown?",
            "Please use the fastest route.",
            "Can you stop near central station?",
            "Can I pay by card?",
            "Can you explain my grammar?",
        ],
    }


def _scan_simulator_behaviors(module, auth):
    client, headers = auth
    scripts = _build_simulator_scripts()
    findings = []
    turns = []

    for context, user_turns in scripts.items():
        previous_ai = ""
        for idx, user_text in enumerate(user_turns, start=1):
            payload = {
                "text": user_text,
                "context": context,
                "lessonLang": "en",
                "practiceMode": "simulator",
                "turnCount": idx,
                "difficulty": "intermediate",
            }
            resp, error_raw = _send_chat_with_retry(client, headers, payload, retries=3)
            status = resp.status_code if resp is not None else 0
            data = (resp.get_json() or {}) if (resp is not None and status == 200) else {}
            ai_text = (data.get("text") or "").strip()
            ai_lower = ai_text.lower()

            turn = {
                "context": context,
                "turn": idx,
                "user": user_text,
                "status": status,
                "ai": ai_text,
            }
            turns.append(turn)

            if status != 200:
                findings.append({
                    "severity": "critical",
                    "type": "http_error",
                    "context": context,
                    "turn": idx,
                    "detail": f"status={status} body={error_raw}",
                })
                continue

            if "feedback" not in data:
                findings.append({
                    "severity": "warning",
                    "type": "missing_feedback_field",
                    "context": context,
                    "turn": idx,
                    "detail": f"keys={list(data.keys())}",
                })

            for marker in TEACHING_MARKERS:
                if marker in ai_lower:
                    findings.append({
                        "severity": "critical",
                        "type": "teaching_leak",
                        "context": context,
                        "turn": idx,
                        "detail": f"marker='{marker}' text='{ai_text[:220]}'",
                    })
                    break

            for marker in ROLE_BREAK_MARKERS:
                if marker in ai_lower:
                    findings.append({
                        "severity": "critical",
                        "type": "role_break",
                        "context": context,
                        "turn": idx,
                        "detail": f"marker='{marker}' text='{ai_text[:220]}'",
                    })
                    break

            for marker in META_REAFFIRM_MARKERS:
                if marker in ai_lower:
                    findings.append({
                        "severity": "warning",
                        "type": "meta_reaffirmation",
                        "context": context,
                        "turn": idx,
                        "detail": f"marker='{marker}' text='{ai_text[:220]}'",
                    })
                    break

            wc = _word_count(ai_text)
            if wc > 45:
                findings.append({
                    "severity": "warning",
                    "type": "too_long",
                    "context": context,
                    "turn": idx,
                    "detail": f"word_count={wc}",
                })

            if ai_text and not ai_text.endswith("?"):
                findings.append({
                    "severity": "critical",
                    "type": "missing_trailing_question",
                    "context": context,
                    "turn": idx,
                    "detail": ai_text[-160:],
                })

            question_count = ai_text.count("?")
            if question_count > 2:
                findings.append({
                    "severity": "warning",
                    "type": "too_many_questions",
                    "context": context,
                    "turn": idx,
                    "detail": f"question_count={question_count}",
                })

            for forbidden in FORBIDDEN_BY_CONTEXT.get(context, []):
                if forbidden in ai_lower:
                    findings.append({
                        "severity": "warning",
                        "type": "domain_drift",
                        "context": context,
                        "turn": idx,
                        "detail": f"forbidden='{forbidden}' text='{ai_text[:220]}'",
                    })
                    break

            if previous_ai and _normalize_text(previous_ai) == _normalize_text(ai_text):
                findings.append({
                    "severity": "warning",
                    "type": "exact_repeat",
                    "context": context,
                    "turn": idx,
                    "detail": ai_text[:220],
                })
            previous_ai = ai_text

    summary = {
        "critical": sum(1 for f in findings if f["severity"] == "critical"),
        "warning": sum(1 for f in findings if f["severity"] == "warning"),
        "total_turns": len(turns),
        "contexts": list(scripts.keys()),
    }

    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "findings": findings,
        "turns": turns,
    }

    report_dir = Path(__file__).resolve().parents[1] / "test_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"simulator_behavior_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report, path


def test_simulator_behavior_scan(auth, module):
    report, report_path = _scan_simulator_behaviors(module, auth)
    critical_findings = [f for f in report["findings"] if f["severity"] == "critical"]
    warnings = [f for f in report["findings"] if f["severity"] == "warning"]
    assert not critical_findings, (
        f"Simulator scan found {len(critical_findings)} critical issues "
        f"and {len(warnings)} warnings. Report: {report_path}"
    )
