from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable, Mapping, Any


FORBIDDEN_GENERIC_PHRASES = [
    "Ajustei a frase para manter o padrão",
    "Ajustei a frase para manter o padrao",
    "Reorganizei a resposta para ficar mais natural",
    "Ajustei verbo",
    "Principais ajustes:",
    "Quando o aluno",
    "o aluno entende",
    "Quando isso ficar claro",
]

MECHANICAL_STARTS = {"Usei", "Corrigi", "Troquei"}
MODAL_TERMS = {"would", "could", "should", "can", "may", "might", "will"}
PRONOUN_TERMS = {"he", "she", "him", "her", "his", "hers"}
FORCE_TERMS = {"too", "very", "really", "not", "never"}
NO_NORMALIZE_PAIRS = [
    ("kid", "child", "kid -> child"),
    ("kids", "children", "kids -> children"),
    ("love", "enjoy", "love -> enjoy"),
    ("good", "positive", "good -> positive"),
    ("movie", "film", "movie -> film"),
    ("big", "large", "big -> large"),
    ("fine", "nice", "fine -> nice"),
    ("so good", "very good", "so good -> very good"),
    ("french bread", "french roll", "French bread -> French roll"),
    ("clear", "bright", "clear -> bright"),
    ("see", "look at", "see -> look at"),
    ("view", "look at", "view -> look at"),
    ("view", "watch", "view -> watch"),
    ("four many hours", "too long", "four many hours -> too long"),
]
ORIGINAL_OK_MARKERS = [
    "tambem esta correto",
    "tambem estava correto",
    "tambem funciona",
    "tambem e natural",
    "tambem natural",
    "nao esta errado",
    "nao estava errado",
    "nao era erro",
    "a palavra original esta correta",
    "a palavra original estava correta",
    "sua palavra estava correta",
]
BOOK_TITLE_CHANGES = [
    ("as mil e uma noites", "one thousand and one nights"),
    ("20.000 leguas submarinas", "twenty thousand leagues under the sea"),
    ("20 000 leguas submarinas", "twenty thousand leagues under the sea"),
    ("rich father", "rich dad poor dad"),
    ("poor father", "rich dad poor dad"),
]
ADDED_INTROS = ["when i go downtown"]
TENSE_PHRASE_CHANGES = [
    ("when i slept", "when i sleep", ("slept", "sleep")),
    ("when i went", "when i go", ("went", "go")),
]


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("’", "'")
    value = re.sub(r"[^a-z0-9']+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def word_bag(text: str) -> Counter[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+(?:[-'][A-Za-zÀ-ÿ0-9]+)?", text or "")
    return Counter(normalize_text(word) for word in words if normalize_text(word))


def contains_phrase(text: str, phrase: str) -> bool:
    return normalize_text(phrase) in normalize_text(text)


def has_downtown_intro_attempt(text: str) -> bool:
    normalized = normalize_text(text)
    return "when i" in normalized and any(fragment in normalized for fragment in ("downtown", "downtow", "downtaw", "dowtown"))


def changed_terms(original: str, corrected: str, terms: set[str]) -> set[str]:
    old_words = word_bag(original)
    new_words = word_bag(corrected)
    return {term for term in terms if old_words.get(term, 0) != new_words.get(term, 0)}


def undocumented_terms(changed: set[str], observation: str, why: str = "") -> set[str]:
    notes = normalize_text(f"{observation} {why}")
    return {term for term in changed if normalize_text(term) not in notes}


def acknowledges_original_was_ok(notes: str, old_value: str = "") -> bool:
    normalized = normalize_text(notes)
    if any(marker in normalized for marker in ORIGINAL_OK_MARKERS):
        return True
    old_norm = normalize_text(old_value)
    if old_norm and old_norm in normalized:
        # Handles accent/encoding variants such as "também está correto" while
        # still requiring the original word to be named in the note.
        return any(marker in normalized for marker in ("corret", "funciona", "natural", "nao estava errad", "nao e erro"))
    return False


def meridiems(text: str) -> list[str]:
    return [match.group(1).lower() for match in re.finditer(r"\b\d{1,2}(?::\d{2})?\s*([ap])\.?m\.?", text or "", re.I)]


def get_value(item: Any, key: str, default: str = "") -> str:
    if isinstance(item, Mapping):
        return str(item.get(key, default) or default)
    return str(getattr(item, key, default) or default)


def validate_correction_quality(items: Iterable[Any], *, min_unique_ratio: float = 0.70) -> list[str]:
    problems: list[str] = []
    observations: list[str] = []
    starts: Counter[str] = Counter()

    for index, item in enumerate(items, 1):
        original = get_value(item, "original")
        corrected = get_value(item, "corrected") or get_value(item, "recommended") or original
        status = get_value(item, "status", "ok")
        observation = get_value(item, "observation")
        why = get_value(item, "why")

        if status not in {"ok", "note", "fix"}:
            problems.append(f"#{index}: status invalido {status!r}")

        if status == "fix":
            old_norm = normalize_text(original.rstrip(".?!"))
            new_norm = normalize_text(corrected.rstrip(".?!"))
            if old_norm == new_norm:
                problems.append(f"#{index}: fix usado para diferenca so de pontuacao/caixa")

        if status == "ok":
            continue

        observations.append(observation)
        first_word = re.match(r"\S+", observation.strip())
        if first_word:
            starts[first_word.group(0)] += 1

        if not observation.strip():
            problems.append(f"#{index}: frase nao-ok sem observacao")

        for phrase in FORBIDDEN_GENERIC_PHRASES:
            if phrase in observation or phrase in why:
                problems.append(f"#{index}: observacao generica proibida")

        if re.search(r"Adicionei '([^']+)', removi '\1'|Removi '([^']+)', adicionei '\2'", observation, re.I):
            problems.append(f"#{index}: observacao contraditoria de adicao/remocao")

        changed_sensitive = set()
        changed_sensitive |= changed_terms(original, corrected, MODAL_TERMS)
        changed_sensitive |= changed_terms(original, corrected, PRONOUN_TERMS)
        changed_sensitive |= changed_terms(original, corrected, FORCE_TERMS)
        missing_sensitive = undocumented_terms(changed_sensitive, observation, why)
        if missing_sensitive:
            problems.append(f"#{index}: troca sensivel sem explicacao: {', '.join(sorted(missing_sensitive))}")

        notes = f"{observation} {why}"
        for old_value, new_value, label in NO_NORMALIZE_PAIRS:
            if contains_phrase(original, old_value) and contains_phrase(corrected, new_value) and not contains_phrase(corrected, old_value):
                if not (
                    contains_phrase(notes, old_value)
                    and contains_phrase(notes, new_value)
                    and acknowledges_original_was_ok(notes, old_value)
                ):
                    problems.append(
                        f"#{index}: palavra valida trocada como se fosse erro; preserve ou explique que tambem estava correta: {label}"
                    )

        for original_title, official_title in BOOK_TITLE_CHANGES:
            if contains_phrase(original, original_title) and contains_phrase(corrected, official_title):
                if not contains_phrase(notes, official_title):
                    problems.append(f"#{index}: titulo oficial em ingles sem explicacao: {official_title}")

        for intro in ADDED_INTROS:
            if contains_phrase(corrected, intro) and not contains_phrase(original, intro):
                if intro == "when i go downtown" and has_downtown_intro_attempt(original):
                    continue
                if not contains_phrase(notes, intro):
                    problems.append(f"#{index}: frase introdutoria adicionada sem explicacao: {intro}")

        for old_phrase, new_phrase, words in TENSE_PHRASE_CHANGES:
            if contains_phrase(original, old_phrase) and contains_phrase(corrected, new_phrase):
                if not all(contains_phrase(notes, word) for word in words):
                    problems.append(f"#{index}: mudanca de tempo verbal sem explicacao: {words[0]} -> {words[1]}")

        old_meridiems = meridiems(original)
        new_meridiems = meridiems(corrected)
        if old_meridiems and new_meridiems and old_meridiems != new_meridiems:
            notes = normalize_text(f"{observation} {why}")
            if "p m" not in notes and "a m" not in notes:
                problems.append(f"#{index}: mudanca a.m./p.m. sem explicacao")

    if observations and len(set(observations)) / len(observations) < min_unique_ratio:
        problems.append(f"observacoes repetidas demais: {len(set(observations))}/{len(observations)} unicas")

    mechanical_count = sum(starts[start] for start in MECHANICAL_STARTS)
    if observations and mechanical_count / len(observations) > 0.50:
        problems.append(
            f"observacoes mecanicas demais: {mechanical_count}/{len(observations)} comecam com Usei/Corrigi/Troquei"
        )

    tambem_count = sum(1 for obs in observations if "tambem" in normalize_text(obs))
    if observations and tambem_count / len(observations) > 0.40:
        problems.append(f"uso excessivo de Tambem nas observacoes: {tambem_count}/{len(observations)}")

    return problems
