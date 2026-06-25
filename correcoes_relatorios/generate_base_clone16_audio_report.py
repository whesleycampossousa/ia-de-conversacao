from __future__ import annotations

import html as html_lib
import importlib.util
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(os.environ.get("EC_REPORT_ROOT", Path(__file__).resolve().parent))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from correction_quality_guardrails import validate_correction_quality

BASE_PATH = Path(os.environ.get("EC_REPORT_BASE", ROOT / "generate_multiatividades_clone16_audio_report.py"))
spec = importlib.util.spec_from_file_location("base_multi", BASE_PATH)
base = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = base
spec.loader.exec_module(base)
BASE_ATTACH_STUDENT_AUDIOS = base.attach_student_audios

REPORT_SLUG = os.environ.get("EC_REPORT_SLUG", "daily")
INPUT_DIR = Path(os.environ.get("EC_REPORT_INPUT_DIR", Path.home() / "Downloads" / "Correcoes hoje"))
DATA_PATH = Path(os.environ.get("EC_REPORT_DATA", ROOT / f"data_{REPORT_SLUG}_corrections.jsonl"))
OUT = Path(os.environ.get("EC_REPORT_OUT", ROOT / f"relatorio_{REPORT_SLUG}_clone16_audio"))
OUTPUT_HTML = Path(os.environ.get("EC_REPORT_HTML", ROOT / f"relatorio_correcao_{REPORT_SLUG}_com_audio_clone16.html"))
REF_AUDIO = Path(
    os.environ.get(
        "EC_CLONE16_REF_AUDIO",
        Path.home()
        / "OneDrive"
        / "Documentos"
        / "Projetos"
        / "Criação Atividades Whatsapp Final"
        / "voices"
        / "clone16_youtube_voice"
        / "reference_22s.wav",
    )
)

ACTIVITIES = {
    "buy_soon": {
        "title": "1ª Atividade - Buy soon",
        "model": "I want to buy...",
        "order": 1,
        "question": "Diga algo que você quer comprar em breve e explique o motivo.",
        "question_en": "What is something you want to buy soon? Why?",
        "question_pt": "Algo que você quer comprar em breve. Por quê?",
    },
    "daily_five_sentences": {
        "title": "2ª Atividade - Mini desafio: 5 sentences",
        "model": "Today... / Tomorrow... / Food... / Study... / Family...",
        "order": 2,
        "question": "Escreva frases livres em inglês: uma sobre hoje, uma sobre amanhã, uma sobre comida, uma sobre estudo e uma sobre família.",
        "question_en": "Challenge: Write 5 sentences. One sentence about today, one about tomorrow, one about food, one about study, and one about family.",
        "question_pt": "Escreva frases livres em inglês: uma sobre hoje, uma sobre amanhã, uma sobre comida, uma sobre estudo e uma sobre família.",
    },
    "confirm": {
        "title": "Atividade a confirmar",
        "model": "Frases para revisão individual.",
        "order": 99,
        "question": "Frases fora dos padrões principais do dia.",
        "question_en": "Individual review.",
        "question_pt": "Revisão individual.",
    },
}


def ts(value: str) -> datetime:
    return datetime.strptime(f"04/06/2026 {value}", "%d/%m/%Y %I:%M %p")


def slug_25(text: str, max_len: int = 58) -> str:
    value = base.normalize_apostrophes(text)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    for old, new in [("can't", "cant"), ("don't", "dont"), ("i'm", "im"), ("i'll", "ill")]:
        value = value.replace(old, new)
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    if not value:
        value = base.hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return value[:max_len].strip("_")


def activity_slug_full(activity: str) -> str:
    return slug_25(activity, 58)


def normalize_text_25(text: str) -> str:
    value = base.normalize_apostrophes(text)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def word_bag(text: str) -> Counter[str]:
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+(?:[-'][A-Za-zÀ-ÿ0-9]+)?", base.normalize_apostrophes(text))
    return Counter(word.lower() for word in words)


def phrase_contains(text: str, phrase: str) -> bool:
    return normalize_text_25(phrase) in normalize_text_25(text)


def changed_terms(original: str, corrected: str, terms: set[str]) -> set[str]:
    old_words = word_bag(original)
    new_words = word_bag(corrected)
    return {term for term in terms if old_words.get(term, 0) != new_words.get(term, 0)}


def undocumented_change_terms(changed: set[str], observation: str, why: str) -> set[str]:
    notes = normalize_text_25(f"{observation} {why}")
    return {term for term in changed if term not in notes}


def meridiems(text: str) -> list[str]:
    return [match.group(1).lower() for match in re.finditer(r"\b\d{1,2}(?::\d{2})?\s*([ap])\.?m\.?", text, re.I)]


def load_data() -> list[dict]:
    rows = []
    with DATA_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def why_from_observation(observation: str) -> str:
    obs = observation.strip()
    if not obs:
        return ""
    low = obs.lower()
    first_sentence = obs.split(".")[0].strip()
    first = first_sentence[:1].lower() + first_sentence[1:] if first_sentence else obs

    if "passado" in low or "yesterday" in low or "domingo" in low:
        return f"Esse ajuste organiza o tempo da história. Neste caso, o ponto central é: {first}."
    if "does" in low or "do " in low or "auxiliar" in low:
        return f"Esse ajuste ajuda a formar perguntas completas no presente simples. Neste caso, o ponto central é: {first}."
    if "refeição" in low or "breakfast" in low or "lunch" in low:
        return f"Esse ajuste deixa mais natural a forma de falar sobre refeições. Neste caso, o ponto central é: {first}."
    if "plural" in low or "vários" in low:
        return f"Esse ajuste mantém a concordância entre quantidade, verbo e pronome. Neste caso, o ponto central é: {first}."
    if "preposição" in low or "to " in low or "of " in low:
        return f"Esse ajuste melhora a ligação entre as palavras. Neste caso, o ponto central é: {first}."
    if "maiúscul" in low:
        return f"Esse ajuste melhora a escrita formal em inglês. Neste caso, o ponto central é: {first}."
    return f"Esse ajuste deixa a frase mais clara e natural. Neste caso, o ponto central é: {first}."


def diff_words(original: str, corrected: str) -> tuple[set[int], list[str]]:
    old_words = [match.group(0) for match in base.INLINE_WORD_RE.finditer(original)]
    new_words = [match.group(0) for match in base.INLINE_WORD_RE.finditer(corrected)]
    old_norm = [normalize_text_25(word) for word in old_words]
    new_norm = [normalize_text_25(word) for word in new_words]
    changed: set[int] = set()
    removed: list[str] = []
    old_set = {word for word in old_norm if word}
    for index, norm in enumerate(new_norm):
        if not norm:
            continue
        if norm not in old_set:
            changed.add(index)
    new_set = {word for word in new_norm if word}
    for word, norm in zip(old_words, old_norm):
        if not norm:
            continue
        if norm not in new_set:
            removed.append(word)
    return changed, removed


def original_diff_sentence(text: str, changed_indices: set[int]) -> str:
    parts = []
    last = 0
    word_index = 0
    for match in base.INLINE_WORD_RE.finditer(text):
        parts.append(base.escape(text[last : match.start()]))
        word = match.group(0)
        if word_index in changed_indices:
            parts.append(f'<span class="diff-original">{base.escape(word)}</span>')
        else:
            parts.append(base.escape(word))
        word_index += 1
        last = match.end()
    parts.append(base.escape(text[last:]))
    return "".join(parts)


def clickable_sentence_diff(text: str, word_lookup: dict[str, dict], changed_indices: set[int]) -> str:
    parts = []
    last = 0
    word_index = 0
    for match in base.INLINE_WORD_RE.finditer(text):
        parts.append(base.escape(text[last : match.start()]))
        word = match.group(0)
        key = base.normalize_apostrophes(word).lower()
        target = word_lookup.get(key)
        extra = " diff-add" if word_index in changed_indices else ""
        if target:
            parts.append(
                f'<span class="audio-word{extra}" role="button" tabindex="0" data-audio="{base.escape(target["id"])}" '
                f'title="Ouvir {base.escape(word)}" aria-label="Ouvir {base.escape(word)}">{base.escape(word)}</span>'
            )
        elif extra:
            parts.append(f'<span class="diff-add">{base.escape(word)}</span>')
        else:
            parts.append(base.escape(word))
        word_index += 1
        last = match.end()
    parts.append(base.escape(text[last:]))
    return "".join(parts)


def removed_words_html(words: list[str]) -> str:
    cleaned: list[str] = []
    ignored = {"1", "2", "3"}
    for word in words:
        norm = normalize_text_25(word)
        if not norm or norm in ignored:
            continue
        if word not in cleaned:
            cleaned.append(word)
    if not cleaned:
        return ""
    spans = " ".join(f'<span class="diff-remove">{base.escape(word)}</span>' for word in cleaned[:10])
    return f'<div class="removed-words"><span>Removidas/alteradas:</span> {spans}</div>'


def correction_tags(phrase) -> list[str]:
    if phrase.status == "ok":
        return ["Tudo certo"]
    text = normalize_text_25(f"{phrase.observation} {phrase.why}")
    tags: list[str] = []
    checks = [
        ("Interpretação", ["interpretei", "assumi", "se a ideia", "se quiser"]),
        ("Alinhar à pergunta", ["pergunta", "completei", "tema exato", "atividade pedia"]),
        ("Ortografia", ["corrigi", "grafia", "typo", "letra", "maiúscula", "minuscula", "minúscula"]),
        ("Gramática", ["verbo", "sujeito", "artigo", "preposicao", "preposição", "plural", "singular", "forma base"]),
        ("Vocabulário", ["expressao", "expressão", "phrasal", "natural", "palavra"]),
        ("Pontuação", ["virgula", "vírgula", "ponto"]),
    ]
    for label, needles in checks:
        if any(normalize_text_25(needle) in text for needle in needles):
            tags.append(label)
    return tags[:4] or ["Revisão"]


def phrase_html_29(group, phrase, index: int, sentence_lookup: dict, word_lookup: dict) -> str:
    status = phrase.status
    sentence_target = sentence_lookup[(phrase.activity, group.key, index)]
    activity_info = ACTIVITIES.get(phrase.activity, {})
    question_en = activity_info.get("question_en") or activity_info.get("question", "Individual review.")
    question_pt = activity_info.get("question_pt") or activity_info.get("question", "Revisão individual.")
    changed_indices: set[int] = set()
    removed: list[str] = []
    original_changed_indices: set[int] = set()
    if status != "ok":
        changed_indices, removed = diff_words(phrase.original, phrase.corrected)
        original_changed_indices, _ = diff_words(phrase.corrected, phrase.original)
    if status == "ok":
        original_sentence = base.clickable_sentence(phrase.original, word_lookup)
    else:
        original_sentence = original_diff_sentence(phrase.original, original_changed_indices)
    tags_html = "".join(f'<span class="correction-tag">{base.escape(tag)}</span>' for tag in correction_tags(phrase))
    lines = [
        f"""
          <div class="line-row">
            <div class="label">Original</div>
            <div class="sentence">{original_sentence}</div>
          </div>""",
    ]
    side_dots = ['<div class="side-dot">&#9679;</div>']
    if status != "ok":
        lines.append(
            f"""
          <div class="line-row">
            <div class="label recommended">Recomendada</div>
            <div class="sentence corrected">{clickable_sentence_diff(phrase.corrected, word_lookup, changed_indices)}{removed_words_html(removed)}</div>
          </div>"""
        )
        side_dots.append('<div class="side-dot recommended">&#9733;</div>')
    lines.append(
        f"""
          <div class="line-row">
            <div class="label">Tradução</div>
            <div class="sentence translation">{base.escape(phrase.translation)}</div>
          </div>"""
    )
    side_dots.append('<div class="side-dot translation">&#9633;</div>')
    if sentence_target["path"].exists():
        lines.append(
            f"""
          <div class="audio-row">
            <div class="label">Áudio modelo</div>
            <audio controls preload="none" src="{base.escape(base.rel(sentence_target["path"]))}"></audio>
          </div>"""
        )
    real_audio_panel = base.phrase_student_audio_panel(group, index)
    if real_audio_panel:
        lines.append(real_audio_panel)
    explain = ""
    if status != "ok":
        explain = f"""
        <div class="explain">
          <div class="explain-piece">
            <div class="explain-icon">!</div>
            <div><strong>O que mudou:</strong>{base.escape(phrase.observation)}</div>
          </div>
          <div class="explain-piece">
            <div class="explain-icon">i</div>
            <div><strong>Por que ajuda:</strong>{base.escape(phrase.why)}</div>
          </div>
        </div>"""
    status_text = base.STATUS[status]["icon"] if status == "ok" else base.STATUS[status]["label"]
    return f"""
      <article class="phrase-card {status}" data-status="{status}">
        <div class="phrase-side">
          <div class="phrase-index">{index}</div>
          {"".join(side_dots)}
        </div>
        <div class="phrase-main">
          <div class="question-card">
            <div class="question-label">Pergunta</div>
            <div class="question-en">{base.escape(question_en)}</div>
            <div class="question-pt">{base.escape(question_pt)}</div>
          </div>
          <h4 class="phrase-title">Frase {index}</h4>
          <div class="correction-tags">{tags_html}</div>
          <div class="phrase-lines">{"".join(lines)}</div>
        </div>
        <div class="status-badge">{status_text}</div>
        {explain}
      </article>"""


def build_phrases_25() -> list:
    phrases = []
    seen: set[tuple[str, str, str]] = set()
    for row in load_data():
        student = row["student"]
        activity = row["activity"]
        original = row["original"]
        dedupe = (student, activity, normalize_text_25(original))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        status = row["status"]
        phrase = base.Phrase(
            original=original,
            activity=activity,
            timestamp=ts(row["time"]),
            author_raw=row["raw_author"],
            author_name=student,
            status=status,
            translation=row["translation"],
            corrected="" if status == "ok" else row["corrected"],
            observation="" if status == "ok" else row["observation"],
            why="" if status == "ok" else (row.get("why") or why_from_observation(row["observation"])),
        )
        phrases.append(phrase)
    return phrases


def student_html_25(group, sentence_lookup: dict, word_lookup: dict) -> str:
    counts = {
        "ok": sum(1 for phrase in group.phrases if phrase.status == "ok"),
        "note": sum(1 for phrase in group.phrases if phrase.status == "note"),
        "fix": sum(1 for phrase in group.phrases if phrase.status == "fix"),
    }
    phrase_markup = "\n".join(
        base.phrase_html(group, phrase, index, sentence_lookup, word_lookup)
        for index, phrase in enumerate(group.phrases, start=1)
    )
    ok_text = f'{counts["ok"]} {"certa" if counts["ok"] == 1 else "certas"}'
    note_text = f'{counts["note"]} {"ajuste leve" if counts["note"] == 1 else "ajustes leves"}'
    fix_text = f'{counts["fix"]} {"correção" if counts["fix"] == 1 else "correções"}'
    has_issues = "true" if counts["note"] or counts["fix"] else "false"
    data_student = slug_25(group.name)
    phone_last4 = sorted(
        {
            re.sub(r"\D", "", phrase.author_raw)[-4:]
            for phrase in group.phrases
            if phrase.author_raw.strip().startswith("+") and re.sub(r"\D", "", phrase.author_raw)
        }
    )
    search = f"{group.name} {group.key} {data_student} {' '.join(phone_last4)} {normalize_text_25(group.name)}"
    return f"""
    <article class="student-card" data-open="false" data-has-issues="{has_issues}" data-student="{base.escape(data_student)}" data-student-name="{base.escape(group.name)}" data-search="{base.escape(search)}">
      <header class="student-head" role="button" tabindex="0" aria-expanded="false">
        <div class="student-id">
          <div class="student-avatar">&#9679;</div>
          <h3>{base.escape(group.name)}</h3>
        </div>
        <div class="student-stats">
          {base.pill_html("ok", "&check;", ok_text)}
          {base.pill_html("note", "!", note_text)}
          {base.pill_html("fix", "&times;", fix_text)}
          <span class="student-toggle" aria-hidden="true">▼</span>
        </div>
      </header>
      <div class="phrases">
        {phrase_markup}
      </div>
    </article>"""


def attach_student_audios_25(by_activity: dict) -> list[dict]:
    previous_allow = os.environ.get("ALLOW_AUDIO_ASSIGNMENT_WARNINGS")
    os.environ["ALLOW_AUDIO_ASSIGNMENT_WARNINGS"] = "1"
    try:
        unclassified = BASE_ATTACH_STUDENT_AUDIOS(by_activity)
    finally:
        if previous_allow is None:
            os.environ.pop("ALLOW_AUDIO_ASSIGNMENT_WARNINGS", None)
        else:
            os.environ["ALLOW_AUDIO_ASSIGNMENT_WARNINGS"] = previous_allow

    def duplicate_multi_activity_audio() -> None:
        groups = [group for activity_groups in by_activity.values() for group in activity_groups]
        for target in groups:
            if target.audios:
                continue
            target_text = " ".join(f"{phrase.original} {base.phrase_text(phrase)}" for phrase in target.phrases)
            best_audio = None
            best_score = 0.0
            for source in groups:
                if source is target or source.name != target.name:
                    continue
                for audio in source.audios:
                    transcript = audio.get("transcript", "")
                    if not transcript:
                        continue
                    score = base.token_score(transcript, target_text)
                    if score > best_score:
                        best_score = score
                        best_audio = audio
            if best_audio and best_score >= 0.65:
                clone = dict(best_audio)
                clone["score"] = round(float(clone.get("score", 0) or 0), 3)
                clone["text_score"] = round(best_score, 3)
                clone["matched_phrases"] = max(int(clone.get("matched_phrases", 1) or 1), 1)
                clone["phrase_index"] = 1
                source_audio_path = ROOT / str(clone.get("path", ""))
                source_name = Path(str(clone.get("file") or source_audio_path.stem)).stem
                target_name = (
                    f"real_{base.activity_slug(target.activity)}_"
                    f"{slug_25(target.name, 24)}_01_{slug_25(source_name, 36)}.mp3"
                )
                target_path = base.STUDENT_CLIP_DIR / target_name
                if source_audio_path.exists() and not target_path.exists():
                    shutil.copy2(source_audio_path, target_path)
                if target_path.exists():
                    clone["path"] = base.rel(target_path)
                target.audios.append(clone)

    def apply_manual_audio_overrides() -> None:
        return

    warning_path = OUT / "audio_assignment_warnings.json"
    if not warning_path.exists():
        duplicate_multi_activity_audio()
        apply_manual_audio_overrides()
        return unclassified
    issues = json.loads(warning_path.read_text(encoding="utf-8"))
    if not issues:
        warning_path.unlink(missing_ok=True)
        duplicate_multi_activity_audio()
        apply_manual_audio_overrides()
        return unclassified

    issue_files = {issue.get("audio") for issue in issues if issue.get("audio")}
    for groups in by_activity.values():
        for group in groups:
            kept = []
            for audio in group.audios:
                audio_file = audio.get("file") or Path(audio.get("path", "")).name
                if audio_file in issue_files:
                    raw_path = base.STUDENT_AUDIO_DIR / audio_file
                    if raw_path.exists() and not any(item.get("file") == audio_file for item in unclassified):
                        unclassified.append(
                            {
                                "file": audio_file,
                                "path": base.rel(raw_path),
                                "transcript": "",
                                "score": 0,
                                "text_score": 0,
                                "matched_phrases": 0,
                                "phrase_index": 1,
                            }
                        )
                    continue
                kept.append(audio)
            group.audios = kept
    warning_path.unlink(missing_ok=True)
    return unclassified


def sync_report_assets() -> None:
    target = OUTPUT_HTML.parent / "assets_relatorios"
    sources = [
        ROOT / "assets_relatorios",
        Path(getattr(base, "ROOT", ROOT)) / "assets_relatorios",
        BASE_PATH.parent / "assets_relatorios",
    ]
    for source in sources:
        if source.exists() and source.resolve() != target.resolve():
            shutil.copytree(source, target, dirs_exist_ok=True)
            return


def validate_phrase_quality_25(phrases: list) -> None:
    problems: list[str] = []
    forbidden = [
        "Ajustei a frase para manter o padrão",
        "Reorganizei a resposta para ficar mais natural",
        "Ajustei verbo",
        "Principais ajustes:",
        "Quando o aluno",
        "o aluno entende",
        "Quando isso ficar claro",
    ]
    modal_terms = {"would", "could", "should", "can", "may", "might", "will"}
    pronoun_terms = {"he", "she", "him", "her", "his", "hers"}
    force_terms = {"too", "very", "really", "not", "never"}
    observations = []
    mechanical_starts = Counter()
    for index, phrase in enumerate(phrases, 1):
        corrected = phrase.corrected or phrase.original
        obs = phrase.observation or ""
        why = phrase.why or ""
        if phrase.status not in {"ok", "note", "fix"}:
            problems.append(f"#{index}: status inválido {phrase.status!r}")
        if phrase.status == "fix":
            old_norm = normalize_text_25(phrase.original.rstrip(".?!"))
            new_norm = normalize_text_25(corrected.rstrip(".?!"))
            if old_norm == new_norm:
                problems.append(f"#{index}: fix usado para diferença só de pontuação/caixa")
        if phrase.status != "ok":
            observations.append(obs)
            first_word = re.match(r"\S+", obs.strip())
            if first_word:
                mechanical_starts[first_word.group(0)] += 1
            if not obs.strip():
                problems.append(f"#{index}: frase não-ok sem observação")
            for item in forbidden:
                if item in obs or item in why:
                    problems.append(f"#{index}: observação genérica proibida")
            if re.search(r"Adicionei '([^']+)', removi '\1'|Removi '([^']+)', adicionei '\2'", obs, re.I):
                problems.append(f"#{index}: observação contraditória de adição/remoção")
            changed_sensitive = set()
            changed_sensitive |= changed_terms(phrase.original, corrected, modal_terms)
            changed_sensitive |= changed_terms(phrase.original, corrected, pronoun_terms)
            changed_sensitive |= changed_terms(phrase.original, corrected, force_terms)
            missing_sensitive = undocumented_change_terms(changed_sensitive, obs, why)
            if missing_sensitive:
                problems.append(f"#{index}: troca sensível sem explicação: {', '.join(sorted(missing_sensitive))}")
            if phrase_contains(phrase.original, "fine") and phrase_contains(corrected, "nice") and not phrase_contains(corrected, "fine"):
                problems.append(f"#{index}: normalização proibida fine -> nice sem necessidade")
            if phrase_contains(phrase.original, "so good") and phrase_contains(corrected, "very good"):
                problems.append(f"#{index}: normalização proibida so good -> very good")
            if phrase_contains(phrase.original, "french bread") and phrase_contains(corrected, "french roll"):
                problems.append(f"#{index}: normalização proibida French bread -> French roll")
            if phrase_contains(phrase.original, "four many hours") and phrase_contains(corrected, "too long"):
                problems.append(f"#{index}: inferência proibida four many hours -> too long")
            old_meridiems = meridiems(phrase.original)
            new_meridiems = meridiems(corrected)
            if old_meridiems and new_meridiems and old_meridiems != new_meridiems:
                notes = normalize_text_25(f"{obs} {why}")
                if "p m" not in notes and "a m" not in notes:
                    problems.append(f"#{index}: mudança a.m./p.m. sem explicação")
    if observations and len(set(observations)) / len(observations) < 0.70:
        problems.append(f"Observações repetidas demais: {len(set(observations))}/{len(observations)} únicas")
    repeated_starts = sum(mechanical_starts[start] for start in ("Usei", "Corrigi", "Troquei"))
    if observations and repeated_starts / len(observations) > 0.50:
        problems.append(f"Observações mecânicas demais no início: {repeated_starts}/{len(observations)} começam com Usei/Corrigi/Troquei")
    problems.extend(validate_correction_quality(phrases))
    if problems:
        raise RuntimeError("Validação pedagógica falhou:\n" + "\n".join(problems[:40]))


def validate_report_25() -> None:
    html = OUTPUT_HTML.read_text(encoding="utf-8")
    decoded = html_lib.unescape(html)
    forbidden = [
        "Ajustei a frase para manter o padrão",
        "Reorganizei a resposta para ficar mais natural",
        "Ajustei verbo",
        "Principais ajustes:",
        "Transcrição automática",
        "frases compatíveis",
        "Match:",
        "Quando o aluno",
        "o aluno entende",
        "Quando isso ficar claro",
    ]
    found = [item for item in forbidden if item in decoded]
    if found:
        raise RuntimeError("Conteúdo proibido detectado no HTML: " + ", ".join(found))
    data_students = re.findall(r'data-student="([^"]+)"', html)
    bad_slugs = [value for value in data_students if " " in html_lib.unescape(value)]
    if bad_slugs:
        raise RuntimeError("data-student com espaço detectado: " + ", ".join(sorted(set(bad_slugs))[:10]))
    refs = re.findall(r'<audio[^>]+src="([^"]+)"', html)
    missing = []
    for ref in refs:
        path = ROOT / html_lib.unescape(ref)
        if not path.exists():
            missing.append(ref)
    if missing:
        raise RuntimeError("Áudios referenciados e não encontrados: " + ", ".join(missing[:10]))


def main() -> None:
    base.INPUT_DIR = INPUT_DIR
    base.OUT = OUT
    base.AUDIO_DIR = OUT / "audio"
    base.SENT_DIR = base.AUDIO_DIR / "sentences"
    base.WORD_DIR = base.AUDIO_DIR / "words"
    base.STUDENT_AUDIO_DIR = base.AUDIO_DIR / "student_submissions"
    base.STUDENT_CLIP_DIR = base.AUDIO_DIR / "student_sentence_clips"
    base.TRANSCRIPT_DIR = OUT / "transcripts"
    base.OUTPUT_HTML = OUTPUT_HTML
    base.MANIFEST_PATH = OUT / "manifest_05_junho_clone16_audio.json"
    base.OCR_RESULTS_PATH = OUT / "ocr_results_05_junho.json"
    base.NAME_MAP_PATH = OUT / "resolved_author_names_05_junho.json"
    base.PHONE_TEMPLATE_PATH = OUT / "phone_to_name_template_05_junho.json"
    base.REF_AUDIO = REF_AUDIO
    base.ACTIVITIES = ACTIVITIES
    for folder in [base.SENT_DIR, base.WORD_DIR, base.STUDENT_AUDIO_DIR, base.STUDENT_CLIP_DIR, base.TRANSCRIPT_DIR]:
        folder.mkdir(parents=True, exist_ok=True)
    base.slug = slug_25
    base.activity_slug = activity_slug_full
    base.normalize_text = normalize_text_25
    base.student_html = student_html_25
    base.phrase_html = phrase_html_29
    base.attach_student_audios = attach_student_audios_25
    base.build_phrases = build_phrases_25
    validate_phrase_quality_25(build_phrases_25())
    base.main()
    sync_report_assets()

    html = OUTPUT_HTML.read_text(encoding="utf-8")
    html = html.replace("06/05/2026", "04/06/2026")
    html = html.replace(
        "com atividades em sequência, busca por aluno e áudios reais associados.",
        "com atividades do dia, busca por aluno e áudios reais associados.",
    )
    html = html.replace(
        "Relatório local para revisão no Opus 4.7 antes de qualquer publicação.",
        "Relatório de revisão para estudar as correções, ouvir os modelos e comparar a própria produção.",
    )
    reading_guide = """
    <section class="reading-guide" aria-label="Roteiro rápido de estudo">
      <div class="guide-main">
        <span class="guide-kicker">Roteiro rápido</span>
        <strong>Procure seu nome, abra seu card e compare cada linha com calma.</strong>
        <p>O destaque mostra o que mudou na versão recomendada. Quando uma palavra sua também estiver correta, a observação precisa dizer isso claramente.</p>
      </div>
      <div class="guide-steps" aria-label="Como ler os destaques">
        <span><b>1</b> Original sublinhado = trecho revisado</span>
        <span><b>2</b> Âmbar = ajuste na recomendada</span>
        <span><b>3</b> Riscado = saiu da frase final</span>
        <span><b>4</b> Áudio = modelo + sua leitura</span>
      </div>
    </section>"""
    html = html.replace('\n    <nav class="tabs-bar" aria-label="Atividades">', f"\n{reading_guide}\n\n    <nav class=\"tabs-bar\" aria-label=\"Atividades\">", 1)
    extra_css = """
    .reading-guide {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(320px, .95fr);
      gap: 14px;
      align-items: stretch;
      margin: 16px 0 18px;
      padding: 16px;
      border: 1px solid rgba(20, 115, 249, .18);
      border-radius: 18px;
      background:
        linear-gradient(135deg, rgba(255,255,255,.98), rgba(239,246,255,.94)),
        radial-gradient(circle at 2% 0%, rgba(20,115,249,.08), transparent 30%);
      box-shadow: 0 16px 34px rgba(7, 17, 63, .08);
    }
    .guide-main {
      display: grid;
      align-content: center;
      gap: 6px;
      padding: 4px 4px 4px 2px;
    }
    .guide-kicker {
      width: max-content;
      padding: 5px 10px;
      border-radius: 999px;
      color: #0b4c90;
      background: #eaf4ff;
      border: 1px solid #cfe2ff;
      font-size: .72rem;
      font-weight: 950;
      text-transform: uppercase;
    }
    .guide-main strong {
      color: #061a4f;
      font-size: 1.02rem;
      line-height: 1.25;
    }
    .guide-main p {
      margin: 0;
      color: #38527f;
      line-height: 1.45;
      font-weight: 650;
    }
    .guide-steps {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 9px;
    }
    .guide-steps span {
      min-height: 44px;
      display: flex;
      align-items: center;
      gap: 9px;
      padding: 9px 11px;
      border: 1px solid rgba(20,115,249,.14);
      border-radius: 13px;
      background: #fff;
      color: #17305e;
      font-size: .86rem;
      font-weight: 820;
      box-shadow: 0 8px 16px rgba(15,39,78,.05);
    }
    .guide-steps b {
      flex: 0 0 auto;
      width: 24px;
      height: 24px;
      display: grid;
      place-items: center;
      border-radius: 999px;
      color: #fff;
      background: #1473f9;
      font-size: .82rem;
    }
    .tabs-bar {
      margin-top: 4px;
    }
    .tab-button {
      position: relative;
      border-left: 6px solid rgba(20,115,249,.38);
      background: linear-gradient(135deg, #fff, #f8fbff);
      transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease;
    }
    .tab-button:hover,
    .tab-button:focus-visible {
      transform: translateY(-1px);
      box-shadow: 0 12px 24px rgba(15, 39, 78, .10);
      outline: none;
    }
    .tab-button.active {
      border-left-color: #063f95;
      box-shadow: 0 14px 28px rgba(20,115,249,.22);
    }
    .student-card {
      border-radius: 16px;
      border-color: rgba(20, 115, 249, .12);
    }
    .student-head {
      background: linear-gradient(135deg, rgba(255,255,255,.99), rgba(248,251,255,.98));
      transition: background .16s ease;
    }
    .student-head:hover {
      background: linear-gradient(135deg, #fff, #eef6ff);
    }
    .student-card[data-open="false"] .student-head {
      border-bottom-color: transparent;
    }
    .student-card[data-open="true"] .student-head {
      border-bottom-color: rgba(20,115,249,.13);
    }
    .student-toggle {
      color: #0b4c90;
      background: #eef6ff;
    }
    .phrases {
      padding: 16px 22px 22px;
      background: linear-gradient(180deg, #fbfdff, #fff);
    }
    .phrase-card {
      grid-template-columns: 54px minmax(0, 1fr) auto;
      gap: 16px;
      padding: 18px 18px 18px 20px;
      border-radius: 16px;
      border-left-width: 7px;
      box-shadow: 0 10px 22px rgba(7,17,63,.05);
    }
    .phrase-title {
      display: inline-flex;
      align-items: center;
      width: max-content;
      padding: 5px 10px;
      border-radius: 999px;
      background: #f1f5fb;
      color: #24436f;
      font-size: .86rem;
    }
    .correction-tags {
      margin: 0 0 12px;
    }
    .correction-tag {
      background: #fff;
      box-shadow: 0 5px 12px rgba(15,39,78,.05);
    }
    .phrase-lines {
      gap: 8px;
    }
    .line-row {
      grid-template-columns: 128px minmax(0, 1fr);
      align-items: start;
      min-height: 0;
      padding: 11px 12px;
      border: 1px solid rgba(19, 50, 91, .09);
      border-radius: 13px;
      background: #fff;
    }
    .line-row:first-child {
      border-top: 1px solid rgba(19, 50, 91, .09);
    }
    .label {
      display: inline-flex;
      align-items: center;
      width: max-content;
      padding: 4px 8px;
      border-radius: 999px;
      background: #f4f7fb;
      color: #395377;
      font-size: .72rem;
      line-height: 1;
    }
    .fix .label.recommended {
      background: var(--red-soft);
    }
    .note .label.recommended {
      background: var(--orange-soft);
    }
    .sentence {
      font-size: 1rem;
      line-height: 1.58;
    }
    .sentence.corrected {
      font-size: 1.04rem;
      line-height: 1.6;
    }
    .sentence.translation {
      color: #315783;
      font-weight: 560;
    }
    .audio-row,
    .student-audio-panel {
      border-radius: 13px;
      background: linear-gradient(135deg, #eef6ff, #fff);
    }
    .explain {
      grid-column: 2 / 4;
      grid-template-columns: 1fr;
      gap: 8px;
      border: 0;
      background: transparent;
      overflow: visible;
    }
    .explain-piece {
      border: 1px solid rgba(20, 115, 249, .15);
      border-radius: 14px;
      background: #fff;
      box-shadow: 0 8px 18px rgba(15,39,78,.05);
    }
    .note .explain-piece {
      border-color: rgba(255, 138, 0, .22);
      background: linear-gradient(135deg, #fff, #fffaf2);
    }
    .fix .explain-piece {
      border-color: rgba(230, 0, 18, .18);
      background: linear-gradient(135deg, #fff, #fff6f7);
    }
    .explain-piece + .explain-piece {
      border-left: 1px solid rgba(20, 115, 249, .15);
    }
    .explain strong {
      color: #061a4f;
      font-size: .86rem;
      text-transform: uppercase;
      letter-spacing: .01em;
    }
    .question-card {
      margin: 0 0 16px;
      padding: 15px 17px;
      border: 1px solid #cfe2ff;
      border-left: 5px solid #2563eb;
      background: linear-gradient(135deg, #f8fbff 0%, #eef6ff 100%);
      border-radius: 16px;
      box-shadow: 0 8px 18px rgba(37, 99, 235, .08);
    }
    .question-label {
      color: #1d4ed8;
      font-size: .78rem;
      font-weight: 950;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .question-en {
      color: #061a4f;
      font-weight: 900;
      line-height: 1.28;
      margin-bottom: 5px;
    }
    .question-pt {
      color: #38527f;
      font-size: .94rem;
      font-weight: 650;
      line-height: 1.35;
      font-style: italic;
    }
    .correction-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin: -4px 0 12px;
    }
    .correction-tag {
      display: inline-flex;
      align-items: center;
      border: 1px solid #bfdbfe;
      background: #eff6ff;
      color: #1d4ed8;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 0.74rem;
      font-weight: 850;
      line-height: 1;
    }
    .diff-add {
      background: #fff4c2;
      border-bottom: 2px solid #d97706;
      border-radius: 5px;
      padding: 0 2px;
      box-decoration-break: clone;
      -webkit-box-decoration-break: clone;
    }
    .audio-word.diff-add {
      box-shadow: 0 0 0 1px rgba(245, 158, 11, .22) inset;
    }
    .diff-original {
      text-decoration-line: underline;
      text-decoration-style: wavy;
      text-decoration-color: #dc2626;
      text-decoration-thickness: 2px;
      text-underline-offset: 4px;
      border-radius: 4px;
      background: linear-gradient(180deg, transparent 58%, rgba(254, 202, 202, .75) 58%);
      padding: 0 1px;
    }
    .removed-words {
      margin-top: 7px;
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      align-items: center;
      font-size: .78rem;
      color: #8a3d00;
      font-weight: 800;
    }
    .diff-remove {
      text-decoration: line-through;
      text-decoration-thickness: 2px;
      background: #fff1f2;
      color: #be123c;
      border: 1px solid #fecdd3;
      border-radius: 999px;
      padding: 2px 7px;
      font-weight: 800;
    }
    @media (max-width: 1180px) {
      .hero-shell {
        grid-template-columns: 1fr;
        min-height: auto;
      }
      .hero-card {
        grid-template-columns: 220px minmax(0, 1fr);
        margin-top: 22px;
      }
      .hero-card h1,
      .hero-card p {
        max-width: 100%;
      }
      .metrics-grid.multi-metrics {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .metrics-grid.multi-metrics .metric-card.red {
        grid-column: auto;
      }
    }
    @media (max-width: 860px) {
      .hero-card {
        grid-template-columns: 1fr;
      }
    }
    @media (max-width: 760px) {
      .reading-guide {
        grid-template-columns: 1fr;
        padding: 13px;
        border-radius: 16px;
      }
      .guide-steps {
        grid-template-columns: 1fr;
      }
      .guide-main strong {
        font-size: .98rem;
      }
      .guide-main p,
      .guide-steps span {
        font-size: .84rem;
      }
      .metrics-grid.multi-metrics {
        grid-template-columns: 1fr;
      }
      .metrics-grid.multi-metrics .metric-card.red {
        grid-column: auto;
      }
      .student-head {
        align-items: flex-start;
      }
      .student-stats {
        width: 100%;
        justify-content: flex-start;
      }
      .student-toggle {
        margin-left: auto;
      }
      .phrases {
        padding: 12px;
      }
      .phrase-card {
        grid-template-columns: 1fr;
        gap: 10px;
        padding: 14px 12px;
      }
      .phrase-side {
        grid-column: 1;
        display: flex;
        flex-direction: row;
        align-items: center;
        justify-content: flex-start;
        gap: 8px;
      }
      .phrase-main {
        grid-column: 1;
        width: 100%;
        min-width: 0;
      }
      .phrase-main > *,
      .phrase-lines,
      .line-row,
      .audio-row,
      .explain {
        width: 100%;
        max-width: 100%;
        box-sizing: border-box;
      }
      .status-badge {
        grid-column: 1;
        justify-self: start;
      }
      .phrase-index {
        width: 38px;
        height: 38px;
        min-width: 38px;
        font-size: 1rem;
      }
      .side-dot {
        width: 24px;
        height: 24px;
        min-width: 24px;
      }
      .line-row {
        display: block;
        grid-column: 1 / -1;
        min-width: 0;
        padding: 12px;
      }
      .line-row .label {
        display: inline-flex;
        width: auto;
        margin: 0 0 8px;
      }
      .sentence {
        display: block;
        width: 100%;
        max-width: 100%;
        min-width: 0;
        overflow-wrap: normal;
        word-break: normal;
        hyphens: none;
      }
      .sentence.corrected {
        font-size: 1rem;
        line-height: 1.62;
      }
      .audio-word,
      .diff-add,
      .diff-original {
        white-space: normal;
        overflow-wrap: normal;
        word-break: normal;
      }
      .removed-words {
        margin-top: 10px;
      }
      .audio-row,
      .student-audio-panel {
        display: block;
        margin-left: 0;
        margin-right: 0;
      }
      .audio-row audio,
      .student-audio-panel audio {
        width: 100%;
        max-width: 100%;
      }
      .explain {
        grid-column: 1 / -1;
        display: grid;
        grid-template-columns: 1fr;
        gap: 8px;
        margin-left: 0;
        margin-right: 0;
      }
      .explain-piece {
        grid-template-columns: 28px minmax(0, 1fr);
        padding: 12px;
      }
      .explain-piece + .explain-piece {
        border-left: 1px solid rgba(20, 115, 249, .15);
      }
      .correction-tags { margin-top: 4px; }
      .question-card { margin-left: -4px; margin-right: -4px; padding: 12px; }
    }
    """
    html = html.replace("</style>", extra_css + "\n</style>", 1)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    validate_report_25()
if __name__ == "__main__":
    main()
