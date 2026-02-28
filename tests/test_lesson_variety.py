#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for structured lesson variety helpers."""

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


def test_diversify_lesson_welcome_avoids_immediate_repeat(module):
    module._lesson_variant_memory.clear()
    base_en = "Welcome to today's lesson!"
    base_pt = "Bem-vindo a aula de hoje!"

    en1, pt1 = module.diversify_lesson_welcome(
        context="coffee_shop",
        lesson_title="Ordering at a Coffee Shop",
        text_en=base_en,
        text_pt=base_pt,
        user_key="student@example.com",
    )
    en2, pt2 = module.diversify_lesson_welcome(
        context="coffee_shop",
        lesson_title="Ordering at a Coffee Shop",
        text_en=base_en,
        text_pt=base_pt,
        user_key="student@example.com",
    )

    assert "Welcome to today's lesson!" in en1
    assert "Welcome to today's lesson!" in en2
    assert en1 != en2
    assert pt1 != pt2


def test_diversify_lesson_instruction_keeps_core_text(module):
    module._lesson_variant_memory.clear()
    base_en = "Choose an option:"
    base_pt = "Escolha uma opcao:"

    en, pt = module.diversify_lesson_instruction(
        context="restaurant",
        layer_title="Starting Your Order",
        text_en=base_en,
        text_pt=base_pt,
        layer_index=0,
        user_key="student@example.com",
    )

    assert "Choose an option:" in en
    assert "Escolha uma opcao:" in pt


def test_diversify_lesson_practice_prompt_keeps_core_text(module):
    module._lesson_variant_memory.clear()
    base_en = "Now try using this phrase!"
    base_pt = "Agora tente usar essa frase!"

    en, pt = module.diversify_lesson_practice_prompt(
        context="hotel",
        text_en=base_en,
        text_pt=base_pt,
        user_key="student@example.com",
    )

    assert "Now try using this phrase!" in en
    assert "Agora tente usar essa frase!" in pt
