#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for Learning mode role clarity and cleanup rules."""

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


@pytest.fixture(scope="module")
def module():
    return _load_api_module()


def test_strip_inline_learning_correction_keeps_useful_phrase(module):
    source = (
        'Great start. A useful phrase is: "I have a reservation under the name Ana." '
        "How many nights will you stay?"
    )
    cleaned = module._strip_inline_learning_correction(source)
    assert "A useful phrase is" in cleaned
    assert "I have a reservation under the name Ana." in cleaned


def test_strip_inline_learning_correction_removes_correction_formula(module):
    source = "Instead of 'I am agree', say: 'I agree.' Great. What do you think?"
    cleaned = module._strip_inline_learning_correction(source)
    assert "Instead of" not in cleaned
    assert cleaned.endswith("?")


def test_repair_learning_phrase_role_replaces_worker_phrase(module):
    source = (
        'Okay, three nights. A useful phrase is: "Can I see your ID, please?" '
        "Now, could you spell your last name for me?"
    )
    repaired, _ = module._repair_learning_phrase_role(source, "", "hotel")
    assert "Can I see your ID, please?" not in repaired
    assert "A useful phrase for you" in repaired
    assert "I have a reservation under the name ___." in repaired


def test_repair_learning_phrase_role_replaces_useful_question_variant(module):
    source = (
        'Perfect, Wesley! Another useful question is: "Can I see your ID, please?" '
        "(Posso ver seu documento de identidade, por favor?) Do you have your ID ready?"
    )
    repaired, _ = module._repair_learning_phrase_role(source, "", "hotel")
    lowered = repaired.lower()
    assert "can i see your id, please?" not in lowered
    assert "another useful phrase for you" in lowered
    assert "i have a reservation under the name ___." in lowered
    assert "eu tenho uma reserva no nome de ___." in lowered
    assert "do you have your id ready?" not in lowered
    assert "how would you answer if the receptionist asks for your id?" in lowered


def test_repair_learning_phrase_role_keeps_student_phrase(module):
    source = (
        'Great. A useful phrase is: "I have a reservation under the name Wesley." '
        "How many nights will you stay?"
    )
    repaired, _ = module._repair_learning_phrase_role(source, "", "hotel")
    assert repaired == source


def test_repair_learning_phrase_role_handles_escaped_newline_prefix(module):
    source = (
        "Yes, breakfast is included and it is served in the lobby from 7:00 AM to 10:00 AM. "
        "\\n\\nUseful phrase: \\ Would you like help with your bags?"
    )
    repaired, _ = module._repair_learning_phrase_role(source, "", "hotel")
    assert "Would you like help with your bags?" not in repaired
    assert "Useful phrase for you" in repaired
    assert "I have a reservation under the name ___." in repaired


def test_extract_json_field_value_handles_escaped_quotes(module):
    raw_text = (
        "{\"en\":\"Breakfast starts at 7:00 AM. Useful phrase: \\\"What is the Wi-Fi password?\\\" "
        "You'll hear from staff: \\\"Here is your room key.\\\"\",\"pt\":\"ok\"}"
    )
    extracted = module._extract_json_field_value(raw_text, "en")
    assert "What is the Wi-Fi password?" in extracted
    assert "You'll hear from staff: Here is your room key." in module._clean_learning_output_artifacts(extracted)


def test_strip_learning_staff_side_lines_keeps_useful_phrase_and_question(module):
    source = (
        "Yes, breakfast is included. You'll hear from staff: Here is your room key. "
        "Useful phrase for you: Could I have the Wi-Fi password? Would you like me to confirm your check-in details?"
    )
    cleaned = module._strip_learning_staff_side_lines(source)
    assert "You'll hear from staff" not in cleaned
    assert "Useful phrase for you" in cleaned
    assert cleaned.endswith("?")


def test_clean_learning_output_artifacts_removes_orphan_useful_phrase_quote(module):
    source = (
        "Here is a useful phrase for you to ask politely: 'Is it possible to have a quiet room? "
        "Would you like help with your bags?"
    )
    cleaned = module._clean_learning_output_artifacts(source)
    assert "useful phrase for you to ask politely: is it possible" in cleaned.lower()
    assert ": '" not in cleaned


def test_sanitize_simulator_meta_text_rewrites_teaching_praise(module):
    source = "Your grammar is perfect. I can teach you another way to say this."
    cleaned = module._sanitize_simulator_meta_text(source, "taxi")
    lowered = cleaned.lower()
    assert "grammar" not in lowered
    assert "teach" not in lowered
    assert "i can help with this service right now." in lowered


def test_resolve_chat_system_prompt_simulator_uses_fallback_without_learning_wrap(module):
    prompt, mode, source = module._resolve_chat_system_prompt(
        context_key="__missing_context_for_simulator_fallback__",
        practice_mode="simulator",
        is_grammar_topic=False,
        objective_text="",
    )
    assert mode == "simulator"
    assert source == "fallback_context_prompt"
    assert "LEARNING MODE (STRICT)" not in prompt
    assert prompt == module.CONTEXT_PROMPTS.get("coffee_shop", "")


def test_console_safe_preview_handles_cp1252_stdout(module, monkeypatch):
    class _DummyStdout:
        encoding = "cp1252"

    monkeypatch.setattr(module.sys, "stdout", _DummyStdout())
    value = module._console_safe_preview("hello 你好 😀", limit=20)
    assert isinstance(value, str)
    assert len(value) <= 20
