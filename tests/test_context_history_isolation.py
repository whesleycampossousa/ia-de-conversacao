#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression test for context/mode history isolation in /api/chat prompt memory.

Run:
    python tests/test_context_history_isolation.py
"""

import importlib.util
from pathlib import Path

import pytest


def _load_api_module():
    project_root = Path(__file__).resolve().parents[1]
    api_path = project_root / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("api_index", api_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extract_history_lines(history_text):
    lines = []
    for raw in (history_text or "").splitlines():
        line = raw.strip()
        if line.startswith("Student:") or line.startswith("You:"):
            lines.append(line)
    return lines


@pytest.fixture(scope="module")
def module():
    return _load_api_module()


def test_filters_by_context_and_mode(module):
    turns = [
        {"user": "Need a latte", "ai": "Hot or iced?", "context": "coffee_shop", "mode": "simulator"},
        {"user": "I lost my card", "ai": "Show your ID", "context": "bank", "mode": "simulator"},
        {"user": "I need to reschedule", "ai": "What day works for you?", "context": "dental_clinic", "mode": "learning"},
        {"user": "Can it be tomorrow?", "ai": "Morning or afternoon?", "context": "dental_clinic", "mode": "learning"},
        # Legacy turn without mode should still be accepted for same context.
        {"user": "No mode field turn", "ai": "Do you prefer Monday?", "context": "dental_clinic"},
        # Same context but wrong mode must be excluded.
        {"user": "Simulator turn", "ai": "Which insurance do you have?", "context": "dental_clinic", "mode": "simulator"},
    ]

    history = module._build_contextual_conversation_history(
        turns,
        context_key="dental_clinic",
        practice_mode="learning",
        max_messages=12
    )

    assert history.startswith("\n### CONVERSATION HISTORY (same context):\n"), "Header format changed unexpectedly"
    lines = _extract_history_lines(history)
    assert lines == [
        "Student: I need to reschedule",
        "You: What day works for you?",
        "Student: Can it be tomorrow?",
        "You: Morning or afternoon?",
        "Student: No mode field turn",
        "You: Do you prefer Monday?",
    ], f"Unexpected contextual history lines: {lines}"


def test_respects_max_messages_cap(module):
    turns = [
        {"user": "Turn 1", "ai": "A1", "context": "gym", "mode": "learning"},
        {"user": "Turn 2", "ai": "A2", "context": "gym", "mode": "learning"},
        {"user": "Turn 3", "ai": "A3", "context": "gym", "mode": "learning"},
    ]
    history = module._build_contextual_conversation_history(
        turns,
        context_key="gym",
        practice_mode="learning",
        max_messages=2
    )
    lines = _extract_history_lines(history)
    assert lines == [
        "Student: Turn 2",
        "You: A2",
        "Student: Turn 3",
        "You: A3",
    ], f"Max messages cap was not applied correctly: {lines}"


def test_returns_empty_history_when_no_match(module):
    turns = [
        {"user": "Bank only", "ai": "Need account?", "context": "bank", "mode": "simulator"},
    ]
    history = module._build_contextual_conversation_history(
        turns,
        context_key="airport",
        practice_mode="learning",
        max_messages=12
    )
    assert history == "", f"Expected empty history when no context matches, got: {history!r}"


def main():
    module_obj = _load_api_module()
    tests = [
        test_filters_by_context_and_mode,
        test_respects_max_messages_cap,
        test_returns_empty_history_when_no_match,
    ]
    for test_fn in tests:
        test_fn(module_obj)
        print(f"[OK] {test_fn.__name__}")
    print("All context history isolation tests passed.")


if __name__ == "__main__":
    main()
