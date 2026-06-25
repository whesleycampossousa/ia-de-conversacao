from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

import numpy as np
import soundfile as sf
import torch
from PIL import Image
import pytesseract
from faster_whisper import WhisperModel
from qwen_tts import Qwen3TTSModel


PROJECT_ROOT = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("EC_REPORT_ROOT", PROJECT_ROOT))
INPUT_DIR = Path(os.environ.get("EC_REPORT_INPUT_DIR", Path.home() / "Downloads" / "Correcoes hoje"))
SMART_CLONER_ROOT = Path(os.environ.get("SMART_CLONER_ROOT", Path.home() / "OneDrive" / "Documentos" / "Projetos" / "Criação Atividades Whatsapp Final"))
REFERENCE_HTML = ROOT / "relatorio_correcao_as_soon_as_5_frases_com_audio_clone16.html"
REFERENCE_CSS = ROOT / "visual_reference.css"
OUT = ROOT / "relatorio_multiatividades_clone16_audio"
AUDIO_DIR = OUT / "audio"
SENT_DIR = AUDIO_DIR / "sentences"
WORD_DIR = AUDIO_DIR / "words"
STUDENT_AUDIO_DIR = AUDIO_DIR / "student_submissions"
STUDENT_CLIP_DIR = AUDIO_DIR / "student_sentence_clips"
TRANSCRIPT_DIR = OUT / "transcripts"
OUTPUT_HTML = ROOT / "relatorio_correcao_multiatividades_com_audio_clone16.html"
MANIFEST_PATH = OUT / "manifest_multiatividades_clone16_audio.json"
OCR_RESULTS_PATH = OUT / "ocr_results.json"
NAME_MAP_PATH = OUT / "resolved_author_names.json"
PHONE_TEMPLATE_PATH = OUT / "phone_to_name_template.json"
REF_AUDIO = Path(os.environ.get("EC_CLONE16_REF_AUDIO", SMART_CLONER_ROOT / "voices" / "clone16_youtube_voice" / "reference.wav"))
TESSERACT_EXE = Path(os.environ.get("TESSERACT_EXE", r"C:\Program Files\Tesseract-OCR\tesseract.exe"))

CACHE_SENT_DIRS = [
    ROOT / "relatorio_as_soon_as_06_05_2026_clone16_audio" / "audio" / "sentences",
    ROOT / "relatorio_as_soon_as_5_frases_clone16_audio" / "audio" / "sentences",
    ROOT / "relatorio_i_am_as_soon_as_clone16_audio" / "audio" / "sentences",
    ROOT / "relatorio_i_can_clone16_audio" / "audio" / "sentences",
]
CACHE_WORD_DIRS = [
    SMART_CLONER_ROOT / "shared_audio_cache" / "words_clone16_youtube_voice",
    ROOT / "relatorio_as_soon_as_06_05_2026_clone16_audio" / "audio" / "words",
    ROOT / "relatorio_as_soon_as_5_frases_clone16_audio" / "audio" / "words",
    ROOT / "relatorio_i_am_as_soon_as_clone16_audio" / "audio" / "words",
    ROOT / "relatorio_i_can_clone16_audio" / "audio" / "words",
    ROOT / "relatorio_as_soon_as_clone16_audio" / "audio" / "words",
]

for folder in [SENT_DIR, WORD_DIR, STUDENT_AUDIO_DIR, STUDENT_CLIP_DIR, TRANSCRIPT_DIR]:
    folder.mkdir(parents=True, exist_ok=True)


STATUS = {
    "ok": {"label": "Tudo certo", "short": "certa", "short_plural": "certas", "icon": "&check;"},
    "note": {"label": "Ajuste leve", "short": "ajuste leve", "short_plural": "ajustes leves", "icon": "!"},
    "fix": {"label": "Corrigir", "short": "correção", "short_plural": "correções", "icon": "&times;"},
}

ACTIVITIES = {
    "favorite": {"title": "My favorite...", "order": 1, "model": "My favorite ___ is ___."},
    "iam": {"title": "I am... and I am...", "order": 2, "model": "I am ___ and I am ___."},
    "as_soon": {"title": "As soon as...", "order": 3, "model": "As soon as I ___, I ___."},
    "age": {"title": "My ... is/was ... years old", "order": 4, "model": "My ___ is ___ years old."},
    "ended_up": {"title": "I ended up...", "order": 5, "model": "I ended up ___ because ___."},
    "used_to": {"title": "I am used to...", "order": 6, "model": "I am used to ___, so ___."},
    "no_matter": {"title": "No matter how...", "order": 7, "model": "No matter how ___, I ___."},
    "confirm": {"title": "Atividade a confirmar", "order": 99, "model": "Frases para revisão manual."},
}


@dataclass
class Phrase:
    original: str
    activity: str
    timestamp: datetime
    author_raw: str
    author_name: str
    status: str
    translation: str
    corrected: str = ""
    observation: str = ""
    why: str = ""


@dataclass
class StudentGroup:
    key: str
    name: str
    activity: str
    phrases: list[Phrase] = field(default_factory=list)
    audios: list[dict] = field(default_factory=list)


def css_from_reference() -> str:
    if REFERENCE_CSS.exists():
        return REFERENCE_CSS.read_text(encoding="utf-8")
    if REFERENCE_HTML.exists():
        text = REFERENCE_HTML.read_text(encoding="utf-8")
        match = re.search(r"<style>(.*?)</style>", text, re.S)
        if match:
            return match.group(1)
    raise RuntimeError("Visual CSS not found. Keep visual_reference.css next to this script.")


EXTRA_CSS = r"""
.page {
  width: min(1360px, calc(100% - 56px));
}
.hero-shell {
  grid-template-columns: minmax(0, 1fr) minmax(360px, 430px);
  gap: 24px;
  min-height: 500px;
  padding: 70px 26px 24px 28px;
  overflow: hidden;
}
.brand-logo {
  top: 16px;
  left: 24px;
  width: 118px;
  height: 118px;
}
.hero-card {
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 30px;
  margin: 44px 0 0;
  padding: 24px 32px 24px 34px;
  min-height: 330px;
}
.hero-asset-wrap {
  min-height: 230px;
}
.hero-asset {
  width: 225px;
}
.hero-card h1 {
  max-width: 440px;
  font-size: clamp(2.35rem, 3.05vw, 3.45rem);
  line-height: 1.12;
}
.hero-card p {
  max-width: 470px;
  margin-top: 18px;
}
.metrics-grid.multi-metrics {
  align-self: stretch;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: minmax(128px, auto);
  gap: 14px;
  padding: 44px 0 0;
}
.metrics-grid.multi-metrics .metric-card {
  min-height: 128px;
  padding: 58px 16px 16px;
}
.metrics-grid.multi-metrics .metric-icon {
  top: 16px;
  left: 16px;
  width: 46px;
  height: 46px;
  font-size: 1.55rem;
}
.metrics-grid.multi-metrics .metric-card strong {
  font-size: 2.35rem;
  line-height: .9;
}
.metrics-grid.multi-metrics .metric-card span {
  font-size: .86rem;
  line-height: 1.24;
}
.metrics-grid.multi-metrics .metric-card::after {
  margin-top: 12px;
}
.metrics-grid.multi-metrics .metric-card.red {
  grid-column: 1 / -1;
  min-height: 118px;
}
.metric-card.red {
  border-color: rgba(239,68,68,.22);
  background: linear-gradient(135deg, rgba(239,68,68,.08), #fff);
}
.metric-card.red .metric-icon {
  background: linear-gradient(135deg, #ef4444, #dc2626);
}
.metric-card.red::after {
  background: #ef4444;
}
.search-panel {
  margin: 16px 0 14px;
  padding: 14px 18px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: rgba(255,255,255,.92);
  box-shadow: var(--shadow-soft);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
}
.search-panel label {
  display: block;
  color: var(--ink);
  font-weight: 900;
  margin-bottom: 6px;
}
.search-input {
  width: 100%;
  border: 1px solid rgba(20,115,249,.24);
  border-radius: 999px;
  padding: 13px 16px;
  color: var(--ink);
  font: inherit;
  font-weight: 750;
  background: #fff;
  outline: none;
}
.search-input:focus {
  border-color: var(--blue);
  box-shadow: 0 0 0 4px rgba(20,115,249,.12);
}
.search-meta {
  color: #526384;
  font-size: .9rem;
  font-weight: 800;
  white-space: nowrap;
}
.tabs-bar {
  margin: 0 0 20px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
  overflow: visible;
  padding: 0;
}
.tab-button {
  border: 1px solid rgba(20,115,249,.18);
  border-radius: 16px;
  background: #fff;
  color: var(--ink);
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 58px;
  padding: 14px 18px;
  font-weight: 900;
  cursor: pointer;
  white-space: normal;
  text-align: left;
  line-height: 1.22;
  box-shadow: 0 8px 18px rgba(15, 39, 78, .06);
}
.tab-button.active {
  background: var(--blue);
  color: #fff;
  border-color: var(--blue);
}
.tab-button.has-match:not(.active) {
  border-color: rgba(16,185,129,.45);
  background: #ecfdf5;
}
.tab-count {
  margin-left: 12px;
  flex: 0 0 auto;
  opacity: .86;
}
.activity-panel {
  display: block;
  margin-bottom: 36px;
  scroll-margin-top: 18px;
}
.activity-panel.active {
  display: block;
}
body.searching .activity-panel[data-search-match="false"] {
  display: none;
}
.activity-summary {
  margin: -6px 0 16px;
  color: #526384;
  font-weight: 750;
}
.student-card[data-hidden="true"] {
  display: none;
}
.student-card {
  overflow: hidden;
}
.student-head {
  cursor: pointer;
  user-select: none;
}
.student-toggle {
  display: inline-grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(20,115,249,.18);
  border-radius: 999px;
  background: #fff;
  color: var(--ink);
  font-weight: 950;
  box-shadow: 0 8px 18px rgba(15,39,78,.06);
}
.student-card[data-open="false"] .phrases {
  max-height: 0;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  margin-top: 0;
}
.student-card[data-open="true"] .phrases {
  max-height: none;
  opacity: 1;
  overflow: visible;
}
.phrases {
  transition: max-height .22s ease, opacity .18s ease;
}
.activity-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0 0 16px;
}
.activity-action {
  border: 1px solid rgba(20,115,249,.18);
  border-radius: 999px;
  background: #fff;
  color: var(--ink);
  padding: 10px 14px;
  font: inherit;
  font-weight: 900;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(15,39,78,.06);
}
.activity-action.active {
  background: #eff6ff;
  border-color: rgba(20,115,249,.35);
  color: var(--blue);
}
.student-card[data-filtered-correct="true"] {
  display: none;
}
.student-audio-panel {
  margin: 0 24px 14px;
  padding: 14px 16px;
  border: 1px solid rgba(20,115,249,.18);
  border-radius: 13px;
  background: linear-gradient(90deg, #eef6ff, #fff);
}
.student-audio-panel strong {
  display: block;
  margin-bottom: 8px;
  color: var(--ink);
}
.student-audio-panel audio {
  width: min(100%, 520px);
}
.student-audio-panel p {
  margin: 8px 0 0;
  color: #526384;
  line-height: 1.45;
}
.unclassified-list {
  display: grid;
  gap: 12px;
}
.unclassified-audio {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: #fff;
  padding: 14px;
  box-shadow: var(--shadow-soft);
}
.unclassified-audio audio {
  width: min(100%, 520px);
}
.audio-word {
  display: inline;
  border: 0;
  border-bottom: 1px dotted rgba(20,115,249,.38);
  border-radius: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: inherit;
  letter-spacing: inherit;
  margin: 0;
  padding: 0;
  appearance: none;
  -webkit-appearance: none;
  cursor: pointer;
}
.audio-word[role="button"] {
  user-select: text;
}
.audio-word:hover,
.audio-word:focus-visible {
  color: var(--blue);
  border-bottom-color: var(--blue);
  outline: none;
}
.audio-bank { display: none; }
@media (max-width: 760px) {
  body { overflow-x: hidden; }
  .page { width: min(100% - 22px, 1240px); }
  .hero-shell {
    grid-template-columns: 1fr;
    min-height: auto;
    padding: 72px 12px 12px;
    overflow: visible;
  }
  .brand-logo { width: 108px; height: 108px; top: 8px; left: 18px; }
  .hero-card {
    grid-template-columns: 1fr;
    margin-top: 10px;
    padding: 22px 18px;
    gap: 14px;
  }
  .hero-card > * { min-width: 0; }
  .hero-asset-wrap { min-height: 180px; }
  .hero-asset { width: 210px; }
  .hero-card h1 {
    max-width: 100%;
    font-size: 2.05rem;
    line-height: 1.14;
    overflow-wrap: break-word;
  }
  .hero-card p {
    max-width: 100%;
    overflow-wrap: break-word;
  }
  .metrics-grid.multi-metrics {
    grid-template-columns: 1fr;
    grid-auto-rows: auto;
    padding-top: 0;
  }
  .metrics-grid.multi-metrics .metric-card.red { grid-column: auto; }
  .search-panel { grid-template-columns: 1fr; }
  .search-meta { white-space: normal; }
  .legend-left {
    display: grid;
    grid-template-columns: 1fr;
    width: 100%;
  }
  .legend-left .pill,
  .legend-bar > .pill {
    width: 100%;
    justify-content: center;
    white-space: normal;
    text-align: center;
  }
  .tabs-bar {
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
    margin: 0 0 20px;
    padding: 0;
    overflow: visible;
  }
  .tab-button {
    width: 100%;
    min-height: 56px;
    justify-content: space-between;
    border-radius: 16px;
    padding: 14px 16px;
    text-align: left;
    white-space: normal;
    line-height: 1.22;
  }
  .tab-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 36px;
    height: 28px;
    margin-left: 14px;
    padding: 0 9px;
    border-radius: 999px;
    background: rgba(20,115,249,.10);
    flex: 0 0 auto;
  }
  .tab-button.active .tab-count {
    background: rgba(255,255,255,.22);
  }
  .activity-panel {
    display: block;
    margin-bottom: 30px;
    scroll-margin-top: 12px;
  }
  body.searching .activity-panel[data-search-match="false"] {
    display: none;
  }
}
@media (max-width: 480px) {
  .hero-card h1 { font-size: 1.92rem; }
  .metrics-grid.multi-metrics { grid-template-columns: 1fr; }
  .metrics-grid.multi-metrics .metric-card {
    min-height: 138px;
  }
}
@media print {
  .student-card,
  .student-card[data-hidden="true"],
  .student-card[data-filtered-correct="true"] {
    display: block !important;
  }
  .student-card .phrases {
    max-height: none !important;
    opacity: 1 !important;
    overflow: visible !important;
  }
  .activity-controls,
  .tabs-bar,
  .search-panel,
  .student-toggle {
    display: none !important;
  }
  .activity-panel {
    display: block !important;
  }
}
"""

CSS = css_from_reference() + EXTRA_CSS


def normalize_apostrophes(text: str) -> str:
    return text.replace(chr(0x2019), "'").replace(chr(0x2018), "'")


def normalize_text(text: str) -> str:
    text = normalize_apostrophes(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def display_author(author: str) -> str:
    raw = author.strip()
    if raw.startswith("+"):
        digits = re.sub(r"\D", "", raw)
        return f"Aluno final {digits[-4:]}" if digits else raw
    raw = re.sub(r"^Cliente\s+", "", raw, flags=re.I).strip()
    raw = re.sub(r"\b(Mensal|Semestral)\b.*$", "", raw, flags=re.I).strip()
    raw = re.sub(
        r"\s+\d{1,2}\s+(Janeiro|Fevereiro|Março|Marco|Abril|Maio|Junho|Julho|Agosto|Setembro|Outubro|Novembro|Dezembro)\b.*$",
        "",
        raw,
        flags=re.I,
    ).strip()
    raw = re.sub(r"\s+\d{1,2}\b.*$", "", raw).strip()
    return raw or author.strip()


def author_key(author: str, resolved_name: str = "") -> str:
    if author.strip().startswith("+"):
        if resolved_name and not resolved_name.startswith("Aluno final"):
            return normalize_text(resolved_name)
        return re.sub(r"\D", "", author)
    return normalize_text(resolved_name or display_author(author))


def slug(text: str, max_len: int = 58) -> str:
    base = normalize_apostrophes(text).lower()
    for old, new in [("can't", "cant"), ("don't", "dont"), ("i'm", "im"), ("i'll", "ill")]:
        base = base.replace(old, new)
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
    if not base:
        base = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return base[:max_len].strip("_")


def activity_slug(activity: str) -> str:
    return slug(activity, 16)


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def plural(count: int, singular: str, plural_form: str) -> str:
    return singular if count == 1 else plural_form


def phrase_text(phrase: Phrase) -> str:
    return phrase.corrected if phrase.status != "ok" else phrase.original


WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?")
INLINE_WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?")


def words_in_text(text: str) -> list[str]:
    return [word for word in WORD_RE.findall(normalize_apostrophes(text)) if word.lower() != "t"]


def word_audio_text(word: str) -> str:
    lower = normalize_apostrophes(word).lower()
    if lower == "i'm":
        return "I am"
    if lower == "i'll":
        return "I will"
    return normalize_apostrophes(word)


def parse_datetime(date_text: str, time_text: str) -> datetime:
    return datetime.strptime(f"{date_text} {time_text}", "%d/%m/%Y %I:%M %p")


def parse_ptt_datetime(path: Path) -> datetime | None:
    match = re.search(r"(\d{4})-(\d{2})-(\d{2}) at (\d{1,2})\.(\d{2})\.(\d{2}) ([AP]M)", path.name, re.I)
    if not match:
        return None
    year, month, day, hour, minute, second, ampm = match.groups()
    return datetime.strptime(f"{year}-{month}-{day} {hour}:{minute}:{second} {ampm.upper()}", "%Y-%m-%d %I:%M:%S %p")


def tesseract_ready() -> bool:
    if TESSERACT_EXE.exists():
        pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
        return True
    found = shutil.which("tesseract")
    if found:
        pytesseract.pytesseract.tesseract_cmd = found
        return True
    return False


def extract_ocr_name(text: str) -> str:
    for line in text.splitlines():
        line = re.sub(r"^[^A-Za-z+]*", "", line).strip()
        match = re.search(r"(Cliente\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s.'-]{2,80})", line)
        if match:
            return display_author(match.group(1))
    return ""


def ocr_screenshots() -> list[dict]:
    pngs = sorted(INPUT_DIR.glob("*.png"))
    if OCR_RESULTS_PATH.exists():
        cached = json.loads(OCR_RESULTS_PATH.read_text(encoding="utf-8"))
        if len(cached) == len(pngs):
            return cached
    if not tesseract_ready():
        PHONE_TEMPLATE_PATH.write_text(json.dumps({"error": "Tesseract not available", "phones": {}}, indent=2), encoding="utf-8")
        raise RuntimeError(f"OCR unavailable. Template written: {PHONE_TEMPLATE_PATH}")
    results = []
    for path in pngs:
        image = Image.open(path)
        text = pytesseract.image_to_string(image, lang="eng")
        results.append({"file": path.name, "name": extract_ocr_name(text), "text": text})
    OCR_RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def read_whatsapp_messages() -> list[dict]:
    txt_files = sorted(INPUT_DIR.glob("*.txt"))
    if len(txt_files) != 1:
        raise RuntimeError(f"Expected 1 TXT file in {INPUT_DIR}, found {len(txt_files)}.")
    text = txt_files[0].read_text(encoding="utf-8")
    # Some WhatsApp exports paste a second header in the middle of the previous line.
    # Normalize that before line-based parsing so two students are not merged.
    text = re.sub(
        r"([^\n])(?=\[\d{1,2}:\d{2} [AP]M, \d{2}/\d{2}/\d{4}\] [^:\n]+:)",
        r"\1\n",
        text,
    )
    lines = text.splitlines()
    messages: list[dict] = []
    current = None
    header_re = re.compile(r"^\[(\d{1,2}:\d{2} [AP]M), (\d{2}/\d{2}/\d{4})\] ([^:]+):\s?(.*)$")
    for line in lines:
        match = header_re.match(line)
        if match:
            if current:
                messages.append(current)
            time_text, date_text, author, first = match.groups()
            current = {
                "timestamp": parse_datetime(date_text, time_text),
                "author": author.strip(),
                "text": first.rstrip(),
            }
        elif current is not None:
            current["text"] += "\n" + line.rstrip()
    if current:
        messages.append(current)
    return messages


def token_score(a: str, b: str) -> float:
    at = set(normalize_text(a).split())
    bt = set(normalize_text(b).split())
    if not at or not bt:
        return 0.0
    overlap = len(at & bt)
    return max(overlap / len(at), overlap / len(bt))


def resolve_phone_names(messages: list[dict], ocr_results: list[dict]) -> dict[str, str]:
    phone_messages = [m for m in messages if m["author"].startswith("+")]
    mapping: dict[str, str] = {}
    for message in phone_messages:
        best = ("", 0.0)
        for ocr in ocr_results:
            if not ocr.get("name"):
                continue
            message_norm = normalize_text(message["text"])
            ocr_norm = normalize_text(ocr.get("text", ""))
            sequence_score = difflib.SequenceMatcher(None, message_norm, ocr_norm).ratio()
            token_overlap = token_score(message["text"], ocr.get("text", ""))
            score = max(sequence_score, token_overlap if sequence_score >= 0.42 else 0.0)
            if score > best[1]:
                best = (ocr["name"], score)
        if best[0] and best[1] >= 0.55:
            mapping[message["author"]] = best[0]
    phones = {m["author"]: mapping.get(m["author"], display_author(m["author"])) for m in phone_messages}
    NAME_MAP_PATH.write_text(json.dumps(phones, ensure_ascii=False, indent=2), encoding="utf-8")
    PHONE_TEMPLATE_PATH.write_text(json.dumps(phones, ensure_ascii=False, indent=2), encoding="utf-8")
    return phones


def split_into_candidate_phrases(text: str) -> list[str]:
    text = normalize_apostrophes(text)
    text = re.sub(r"\r", "", text)
    candidates = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower() == "foto":
            continue
        line = re.sub(r"^\s*[_\-•]+\s*", "", line)
        line = re.sub(r"^\s*\d+[\.)]\s*", "", line)
        line = re.sub(r"\s+-\s+", "\n", line)
        line = re.sub(
            r"(?i)\s+(?=(My favorite|I am used|I'm used|I’m used|As soon|I soon as|No matter|I ended up|I end up|My [A-Za-z-]+ (?:is|was|were) ))",
            "\n",
            line,
        )
        for part in line.splitlines():
            part = re.sub(r"^\s*[_\-•]+\s*", "", part).strip()
            if not part or part.lower() == "foto":
                continue
            if len(part.split()) < 3:
                continue
            candidates.append(part)
    return candidates


def classify_activity(text: str) -> str:
    n = normalize_text(text)
    if n.startswith("my favorite"):
        return "favorite"
    if re.match(r"^i(?: am|'m) .+ and i(?: am|'m) ", n):
        return "iam"
    if n.startswith("as soon") or n.startswith("i soon as"):
        return "as_soon"
    if re.match(r"^my .+ (is|was|were) .+ years old", n):
        return "age"
    if n.startswith("i ended up") or n.startswith("i end up"):
        return "ended_up"
    if n.startswith("i am used") or n.startswith("i m used"):
        return "used_to"
    if n.startswith("no matter"):
        return "no_matter"
    return "confirm"


def cap_i(text: str) -> str:
    text = re.sub(r"\bi\b", "I", text)
    text = re.sub(r"\bi'm\b", "I'm", text, flags=re.I)
    text = re.sub(r"\bi'll\b", "I'll", text, flags=re.I)
    text = re.sub(r"\benglish\b", "English", text, flags=re.I)
    text = re.sub(r"\bfrench\b", "French", text, flags=re.I)
    text = re.sub(r"\bspanish\b", "Spanish", text, flags=re.I)
    for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        text = re.sub(rf"\b{day}\b", day.title(), text, flags=re.I)
    text = re.sub(r"\bgod\b", "God", text, flags=re.I)
    text = re.sub(r"\bbible\b", "Bible", text, flags=re.I)
    return text


def tidy_sentence(text: str) -> str:
    text = normalize_apostrophes(text.strip())
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r",(?=\S)", ", ", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = cap_i(text)
    if text and text[-1] not in ".!?":
        text += "."
    return text


ADJ_TRANSLATIONS = {
    "grateful": "grato(a)", "happy": "feliz", "focused": "focado(a)", "tired": "cansado(a)",
    "calm": "calmo(a)", "busy": "ocupado(a)", "sad": "triste", "sick": "doente",
    "curious": "curioso(a)", "worried": "preocupado(a)", "confident": "confiante",
    "excited": "animado(a)", "motivated": "motivado(a)", "hungry": "com fome",
    "thirsty": "com sede", "sleepy": "com sono",
}


def translation_for(activity: str, corrected: str) -> str:
    c = corrected.rstrip(".")
    if activity == "favorite":
        match = re.match(r"My favorite (.+?) is (.+)", c, re.I)
        if match:
            return f"Meu/Minha {match.group(1)} favorito(a) é {match.group(2)}."
    if activity == "age":
        match = re.match(r"My (.+?) (is|was|were) (.+?) years? old", c, re.I)
        if match:
            tense = "tinha" if match.group(2).lower() in {"was", "were"} else "tem"
            return f"Meu/Minha {match.group(1)} {tense} {match.group(3)} anos."
    if activity == "iam":
        parts = re.split(r"\s+and\s+", c, flags=re.I)
        translated = []
        for part in parts:
            cleaned = re.sub(r"^I(?: am|'m)\s+", "", part, flags=re.I).strip()
            words = [ADJ_TRANSLATIONS.get(w.lower(), w) for w in cleaned.split()]
            translated.append(" ".join(words))
        if translated:
            return "Eu estou " + " e estou ".join(translated) + "."
    if activity == "as_soon":
        return "Assim que eu fizer a primeira ação, eu faço a segunda ação."
    if activity == "used_to":
        return "Eu estou acostumado(a) a essa rotina, então isso faz parte da minha vida."
    if activity == "ended_up":
        return "Eu acabei fazendo isso por causa da situação."
    if activity == "no_matter":
        return "Não importa a situação, eu continuo fazendo isso."
    return "Tradução para revisão."


FAVORITE_CATEGORY_PT = {
    "animal": "animal", "anime": "anime", "band": "banda", "book": "livro",
    "city outside Salvador": "cidade fora de Salvador", "color": "cor", "day": "dia",
    "drawing": "desenho", "drink": "bebida", "exercise": "exercício", "food": "comida",
    "fruit": "fruta", "hobby": "hobby", "instrument": "instrumento", "language": "idioma",
    "makeup": "maquiagem", "makeup item": "item de maquiagem", "Manhwa": "manhwa",
    "meal": "refeição", "meat": "carne", "metalcore band": "banda de metalcore",
    "movie": "filme", "pet": "animal de estimação", "place": "lugar", "season": "estação do ano",
    "series": "série", "soccer team": "time de futebol", "song": "música",
    "sport": "esporte", "sport to play": "esporte favorito para jogar",
    "sport to watch": "esporte favorito para assistir", "Story": "história",
    "subject": "matéria", "sweet": "doce", "time of day": "horário do dia",
    "trip": "viagem", "work": "trabalho",
}

VALUE_PT = {
    "a dog": "um cachorro", "action movie": "filme de ação", "American football (NFL)": "futebol americano (NFL)",
    "barbecue": "churrasco", "basketball": "basquete", "the beach": "a praia", "beach": "praia",
    "black": "preto", "Black": "preto", "black panties": "Black Pantera", "blue": "azul",
    "bodybuilding": "musculação", "cat": "gato", "cats and dogs": "gatos e cachorros",
    "chocolate": "chocolate", "church": "igreja", "coffee": "café", "cruzeiro": "Cruzeiro",
    "Dog": "cachorro", "dog": "cachorro", "fish": "peixe", "football": "futebol", "soccer": "futebol",
    "Friday": "sexta-feira", "green": "verde", "home": "casa", "my home": "minha casa",
    "Japanese food": "comida japonesa", "Jiu-Jitsu": "jiu-jitsu", "Juice": "suco", "juice": "suco",
    "lively music": "música animada", "mango": "manga", "mascara": "rímel", "math": "matemática",
    "milk": "leite", "morning": "manhã", "orange juice": "suco de laranja", "Orange Juice": "suco de laranja",
    "parrot": "papagaio", "pasta": "massa", "piano": "piano", "pop song": "música pop",
    "Portuguese": "português", "potato": "batata", "Pretty Woman": "Uma Linda Mulher",
    "purple": "roxo", "reading": "ler", "rice with beans": "arroz com feijão",
    "Rice and Bean with beef": "arroz e feijão com carne", "rump steak": "picanha",
    "soda": "refrigerante", "Spanish": "espanhol", "sparkling water with lemon": "água com gás com limão",
    "spring": "primavera", "strawberry": "morango", "sushi": "sushi", "swimming": "natação",
    "the mountains": "as montanhas", "today": "hoje", "traveling": "viajar", "walking": "caminhada",
    "water": "água", "Wednesday": "quarta-feira", "white": "branco", "wine": "vinho", "running": "corrida",
}

FAVORITE_LABEL_PT = {
    "animal": "Meu animal favorito", "anime": "Meu anime favorito", "band": "Minha banda favorita",
    "book": "Meu livro favorito", "city outside Salvador": "Minha cidade favorita fora de Salvador",
    "color": "Minha cor favorita", "day": "Meu dia favorito", "drawing": "Meu desenho favorito",
    "drink": "Minha bebida favorita", "exercise": "Meu exercício favorito", "food": "Minha comida favorita",
    "fruit": "Minha fruta favorita", "hobby": "Meu hobby favorito", "instrument": "Meu instrumento favorito",
    "language": "Meu idioma favorito", "makeup": "Minha maquiagem favorita",
    "makeup item": "Meu item de maquiagem favorito", "Manhwa": "Meu manhwa favorito",
    "meal": "Minha refeição favorita", "meat": "Minha carne favorita",
    "metalcore band": "Minha banda de metalcore favorita", "movie": "Meu filme favorito",
    "pet": "Meu animal de estimação favorito", "place": "Meu lugar favorito",
    "season": "Minha estação do ano favorita", "series": "Minha série favorita",
    "soccer team": "Meu time de futebol favorito", "song": "Minha música favorita",
    "sport": "Meu esporte favorito", "sport to play": "Meu esporte favorito para jogar",
    "sport to watch": "Meu esporte favorito para assistir", "Story": "Minha história favorita",
    "subject": "Minha matéria favorita", "sweet": "Meu doce favorito",
    "time of day": "Meu horário favorito do dia", "trip": "Minha viagem favorita",
    "work": "Meu trabalho favorito",
}

FAMILY_PT = {
    "baby": ("Meu bebê", "tem", "tinha"), "best friend": ("Meu/minha melhor amigo(a)", "tem", "tinha"),
    "bird": ("Meu pássaro", "tem", "tinha"), "brother": ("Meu irmão", "tem", "tinha"),
    "cat": ("Meu gato", "tem", "tinha"), "cats": ("Meus gatos", "têm", "tinham"),
    "cousin": ("Meu/minha primo(a)", "tem", "tinha"), "daughter": ("Minha filha", "tem", "tinha"),
    "dog": ("Meu cachorro", "tem", "tinha"), "father": ("Meu pai", "tem", "tinha"),
    "father-in-law": ("Meu sogro", "tem", "tinha"), "friend": ("Meu/minha amigo(a)", "tem", "tinha"),
    "husband": ("Meu marido", "tem", "tinha"), "mother": ("Minha mãe", "tem", "tinha"),
    "niece": ("Minha sobrinha", "tem", "tinha"), "rabbit": ("Meu coelho", "tem", "tinha"),
    "sister": ("Minha irmã", "tem", "tinha"), "sister-in-law": ("Minha cunhada", "tem", "tinha"),
    "son": ("Meu filho", "tem", "tinha"),
}

NUMBER_PT = {
    "one": "um", "two": "dois", "three": "três", "four": "quatro", "five": "cinco",
    "six": "seis", "seven": "sete", "eight": "oito", "nine": "nove", "ten": "dez",
    "eleven": "onze", "twelve": "doze", "fifteen": "quinze", "sixteen": "dezesseis",
    "seventeen": "dezessete", "eighteen": "dezoito", "nineteen": "dezenove", "twenty": "vinte",
    "thirty-three": "trinta e três", "thirty-four": "trinta e quatro", "thirty-nine": "trinta e nove",
    "forty": "quarenta", "forty-two": "quarenta e dois", "sixty-eight": "sessenta e oito",
    "seventy": "setenta", "seventy-eight": "setenta e oito", "ninety-one": "noventa e um",
}

PHRASE_PT = {
    "as soon as i wake up, i have breakfast": "Assim que eu acordo, eu tomo café da manhã.",
    "as soon as i take a shower, i dry my hair": "Assim que eu tomo banho, eu seco meu cabelo.",
    "as soon as i finish practicing english, i read a good book": "Assim que eu termino de praticar inglês, eu leio um bom livro.",
    "as soon as i feed my pets, i eat my lunch": "Assim que eu alimento meus pets, eu almoço.",
    "as soon as i have dinner, i watch a movie": "Assim que eu janto, eu assisto a um filme.",
    "as soon as i get home, i have some lunch": "Assim que eu chego em casa, eu almoço.",
    "as soon as i exercise, i take a shower": "Assim que eu me exercito, eu tomo banho.",
    "as soon as i buy something online, i regret it": "Assim que eu compro algo online, eu me arrependo.",
    "as soon as i earn my wage, i pay all my bills": "Assim que eu recebo meu salário, eu pago todas as minhas contas.",
    "as soon as i read a new word, i look up its pronunciation and meaning": "Assim que eu leio uma palavra nova, eu procuro a pronúncia e o significado dela.",
    "as soon as i read a new word, i search its pronunciation and meaning": "Assim que eu leio uma palavra nova, eu busco a pronúncia e o significado dela.",
    "as soon as i get home, i take a quick shower": "Assim que eu chego em casa, eu tomo um banho rápido.",
    "as soon as i get home, i make lunch and then i go to the gym": "Assim que eu chego em casa, eu faço almoço e depois vou para a academia.",
    "as soon as i finish my work, i clean my tools": "Assim que eu termino meu trabalho, eu limpo minhas ferramentas.",
    "as soon as i wake up, i thank god": "Assim que eu acordo, eu agradeço a Deus.",
    "as soon as i wake up, i brush my teeth": "Assim que eu acordo, eu escovo os dentes.",
    "as soon as i arrive at the airport, i check in": "Assim que eu chego ao aeroporto, eu faço check-in.",
    "as soon as i start my work, i check my e-mails": "Assim que eu começo meu trabalho, eu verifico meus e-mails.",
    "as soon as i start watching my soccer team, i feel angry": "Assim que eu começo a assistir ao meu time de futebol, eu fico bravo.",
    "as soon as i finish my daily work, i need to rest my mind": "Assim que eu termino meu trabalho diário, eu preciso descansar a mente.",
    "as soon as i finish work, i pick up my son from school": "Assim que eu termino o trabalho, eu busco meu filho na escola.",
    "as soon as i finish exercising, i drink water": "Assim que eu termino de me exercitar, eu bebo água.",
    "as soon as i wake up, i take a shower": "Assim que eu acordo, eu tomo banho.",
    "as soon as i have coffee, i go to work": "Assim que eu tomo café, eu vou trabalhar.",
    "as soon as i finish running, i check my phone": "Assim que eu termino de correr, eu olho meu celular.",
    "as soon as i wake up, i wash my face": "Assim que eu acordo, eu lavo o rosto.",
    "as soon as i go to work, i thank god": "Assim que eu vou para o trabalho, eu agradeço a Deus.",
    "as soon as i get home, i play with my dog": "Assim que eu chego em casa, eu brinco com meu cachorro.",
    "as soon as i finish dinner, i relax": "Assim que eu termino o jantar, eu relaxo.",
    "as soon as i go to bed, i sleep": "Assim que eu vou para a cama, eu durmo.",
    "as soon as i arrive at the office, i turn on my computer": "Assim que eu chego ao escritório, eu ligo meu computador.",
    "as soon as i get home, i eat and take a shower": "Assim que eu chego em casa, eu como e tomo banho.",
    "as soon as i finish my walk outside, i feel tired": "Assim que eu termino minha caminhada lá fora, eu me sinto cansado.",
    "as soon as i finish my work, i come back home": "Assim que eu termino meu trabalho, eu volto para casa.",
    "as soon as i get home, i take a long hot shower and then i have dinner": "Assim que eu chego em casa, eu tomo um banho longo e quente e depois janto.",
    "as soon as i finish work, i take the road to get home": "Assim que eu termino o trabalho, eu pego a estrada para voltar para casa.",
    "as soon as i wake up, i get out of bed and take a shower then after i get dressed, i start a great new day": "Assim que eu acordo, eu saio da cama e tomo banho. Depois que me visto, começo um ótimo novo dia.",
    "as soon as i finish my homework, i take a shower": "Assim que eu termino minha lição de casa, eu tomo banho.",
    "as soon as i finish reading my bible, i talk to you": "Assim que eu termino de ler minha Bíblia, eu falo com você.",
    "as soon as i finish brushing my teeth, i go to sleep": "Assim que eu termino de escovar os dentes, eu vou dormir.",
    "as soon as i write my book, i'll have lunch with you": "Assim que eu escrever meu livro, eu vou almoçar com você.",
    "as soon as i do the interview, i call you": "Assim que eu fizer a entrevista, eu ligo para você.",
    "as soon as i get home, i'm going to the gym": "Assim que eu chegar em casa, eu vou para a academia.",
    "as soon as i finish my work, i try to study english": "Assim que eu termino meu trabalho, eu tento estudar inglês.",
    "as soon as i get an answer from him, i'll report back to you": "Assim que eu receber uma resposta dele, eu te aviso.",
    "as soon as i receive my money, i'll pay you": "Assim que eu receber meu dinheiro, eu vou te pagar.",
    "as soon as i learn french, i could move to another country": "Assim que eu aprender francês, eu poderia me mudar para outro país.",
    "as soon as i come back from the office, i eat a quick snack": "Assim que eu volto do escritório, eu como um lanche rápido.",
    "as soon as i finish my english study, i feel more confident to talk with friends": "Assim que eu termino meu estudo de inglês, eu me sinto mais confiante para falar com amigos.",
    "as soon as i have a question about english class, i ask the teacher for help": "Assim que eu tenho uma dúvida sobre a aula de inglês, eu peço ajuda ao professor.",
    "as soon as i receive my salary, i pay my bills": "Assim que eu recebo meu salário, eu pago minhas contas.",
    "as soon as i study english, i feel that i can achieve fluency": "Assim que eu estudo inglês, eu sinto que posso alcançar a fluência.",
    "as soon as i finish any meal, i brush my teeth": "Assim que eu termino qualquer refeição, eu escovo os dentes.",
    "as soon as i get up, i wake up my kids too": "Assim que eu levanto, eu acordo meus filhos também.",
    "as soon as my phone goes off, i turn off the alarm": "Assim que meu celular toca, eu desligo o alarme.",
    "as soon as i hug my daughter, she tries to tickle me": "Assim que eu abraço minha filha, ela tenta me fazer cócegas.",
    "as soon as i study english, i get better": "Assim que eu estudo inglês, eu melhoro.",
    "as soon as i finish my work, i'm going to study english": "Assim que eu termino meu trabalho, eu vou estudar inglês.",
    "as soon as i finish the housework, i'll eat out": "Assim que eu termino as tarefas de casa, eu vou comer fora.",
    "as soon as i get home, i'm going to watch a movie": "Assim que eu chegar em casa, eu vou assistir a um filme.",
    "as soon as i have dinner, i'll call my mother": "Assim que eu jantar, eu vou ligar para minha mãe.",
    "as soon as i have lunch, i'll take a nap": "Assim que eu almoçar, eu vou tirar um cochilo.",
    "i am used to waking up at 6 am, so i usually go for a walk on the beach in the morning": "Eu estou acostumado(a) a acordar às 6 da manhã, então geralmente caminho na praia de manhã.",
    "i am used to studying english a lot every day, so i feel more and more confident": "Eu estou acostumado(a) a estudar muito inglês todos os dias, então me sinto cada vez mais confiante.",
    "i am used to practicing aerobic exercise, so i feel amazing": "Eu estou acostumado(a) a praticar exercício aeróbico, então me sinto muito bem.",
    "i am used to helping my son with his homework, so i learn new things every day": "Eu estou acostumado(a) a ajudar meu filho com a lição de casa, então aprendo coisas novas todos os dias.",
    "i am used to going out with my family on weekends, so we have a lot of fun": "Eu estou acostumado(a) a sair com minha família nos fins de semana, então nós nos divertimos muito.",
    "i am used to running twice a week, so i stay healthy": "Eu estou acostumado(a) a correr duas vezes por semana, então me mantenho saudável.",
    "i am used to eating food without sugar, so not eating sweets isn't a problem": "Eu estou acostumado(a) a comer comida sem açúcar, então não comer doces não é um problema.",
    "i am used to getting up early every day, so i have a long day": "Eu estou acostumado(a) a levantar cedo todos os dias, então meu dia rende bastante.",
    "i am used to speaking out loud, so speaking to a crowd is easy": "Eu estou acostumado(a) a falar em voz alta, então falar para um público é fácil.",
    "i am used to wearing sun cream, so i don't get sunburned": "Eu estou acostumado(a) a usar protetor solar, então não fico queimado(a) de sol.",
    "i am used to living near the sea, so i don't want to go back to my hometown in the interior of minas gerais": "Eu estou acostumado(a) a morar perto do mar, então não quero voltar para minha cidade natal no interior de Minas Gerais.",
    "i am used to living alone, so i don't like having many visitors": "Eu estou acostumado(a) a morar sozinho(a), então não gosto de receber muitas visitas.",
    "i am used to doing everything myself, so i don't like asking for help": "Eu estou acostumado(a) a fazer tudo sozinho(a), então não gosto de pedir ajuda.",
    "i am used to styling my own hair, so i don't go to hair salons": "Eu estou acostumado(a) a arrumar meu próprio cabelo, então não vou a salões.",
    "i'm used to reading a book before sleeping, so this is a habit for me": "Eu estou acostumado(a) a ler um livro antes de dormir, então isso é um hábito para mim.",
    "i'm used to preparing my breakfast in the morning, so my daily routine starts after this": "Eu estou acostumado(a) a preparar meu café da manhã de manhã, então minha rotina diária começa depois disso.",
    "i'm used to riding a bike at night, so finishing my day with this activity is rewarding for me": "Eu estou acostumado(a) a andar de bicicleta à noite, então terminar meu dia com essa atividade é gratificante para mim.",
    "i am used to studying every day, so activities don't bother me": "Eu estou acostumado(a) a estudar todos os dias, então as atividades não me incomodam.",
    "i am used to eating salad, so eating vegetables is frequent in my life": "Eu estou acostumado(a) a comer salada, então comer vegetais é frequente na minha vida.",
    "i am used to practicing exercises every single day, so going to the gym is a pleasure for me": "Eu estou acostumado(a) a praticar exercícios todos os dias, então ir à academia é um prazer para mim.",
    "i am used to listening to music, so this habit is part of my routine": "Eu estou acostumado(a) a ouvir música, então esse hábito faz parte da minha rotina.",
    "i am used to studying english every day, so i keep in my mind everything that i learned": "Eu estou acostumado(a) a estudar inglês todos os dias, então mantenho na mente tudo que aprendi.",
    "i am used to listening to music when i'm going to run, so i feel more motivated to do it": "Eu estou acostumado(a) a ouvir música quando vou correr, então me sinto mais motivado(a) para fazer isso.",
    "i am used to taking a shower before going to bed, so it helps me sleep better": "Eu estou acostumado(a) a tomar banho antes de dormir, então isso me ajuda a dormir melhor.",
    "i'm used to jogging, so running a marathon is not a problem": "Eu estou acostumado(a) a correr devagar, então correr uma maratona não é um problema.",
    "i'm used to spicy foods, so eating mexican food is ok for me": "Eu estou acostumado(a) a comidas apimentadas, então comer comida mexicana é tranquilo para mim.",
    "i'm used to heights, so i am not afraid of roller coasters": "Eu estou acostumado(a) a alturas, então não tenho medo de montanhas-russas.",
    "i ended up putting off my trip to the beach on the weekend because the weather was rainy": "Eu acabei adiando minha viagem para a praia no fim de semana porque o tempo estava chuvoso.",
    "i ended up sleeping during the movie because it was so boring": "Eu acabei dormindo durante o filme porque ele era muito chato.",
    "i end up sleeping during the movie because it was so boring": "Eu acabei dormindo durante o filme porque ele era muito chato.",
    "i ended up working from home because the power at the office was going to be shut off": "Eu acabei trabalhando de casa porque a energia do escritório seria desligada.",
    "i ended up with this item because i forgot to change it before it expired": "Eu acabei ficando com esse item porque esqueci de trocar antes de vencer.",
    "i ended up watching that movie because my wife convinced me": "Eu acabei assistindo àquele filme porque minha esposa me convenceu.",
    "i ended up going to the beach because the weather was hot": "Eu acabei indo para a praia porque o tempo estava quente.",
    "i ended up buying a new dress because i went to a fashion party": "Eu acabei comprando um vestido novo porque fui a uma festa de moda.",
    "i ended up watching this movie again because it was amazing": "Eu acabei assistindo a este filme de novo porque ele era incrível.",
    "no matter how i'm doing, i need to speak every day": "Não importa como eu esteja, eu preciso falar todos os dias.",
}


PHRASE_PT_NORM = {normalize_text(key): value for key, value in PHRASE_PT.items()}


def translation_for(activity: str, corrected: str) -> str:
    c = tidy_sentence(corrected).rstrip(".")
    override = PHRASE_PT_NORM.get(normalize_text(c))
    if override:
        return override
    if activity == "favorite":
        match = re.match(r"My favorite (.+?) (?:is|was) (.+)", c, re.I)
        if match:
            category = match.group(1).strip()
            value = match.group(2).strip()
            value_pt = VALUE_PT.get(value, value)
            verb = "foi" if re.search(r"\bwas\b", c, re.I) else "é"
            label = FAVORITE_LABEL_PT.get(category, f"Meu/Minha {FAVORITE_CATEGORY_PT.get(category, category)} favorito(a)")
            return f"{label} {verb} {value_pt}."
    if activity == "age":
        match = re.match(r"My (.+?) (is|was|were) (.+?) years? old", c, re.I)
        if match:
            person = match.group(1).strip()
            be = match.group(2).lower()
            age = NUMBER_PT.get(match.group(3).strip(), match.group(3).strip())
            owner, present, past = FAMILY_PT.get(person, (f"Meu/Minha {person}", "tem", "tinha"))
            verb = past if be in {"was", "were"} else present
            return f"{owner} {verb} {age} anos."
    if activity == "iam":
        parts = re.split(r"\s+and\s+", c, flags=re.I)
        translated = []
        for part in parts:
            cleaned = re.sub(r"^I(?: am|'m)\s+", "", part, flags=re.I).strip()
            words = [ADJ_TRANSLATIONS.get(w.lower(), w) for w in cleaned.split()]
            translated.append(" ".join(words))
        if translated:
            return "Eu estou " + " e estou ".join(translated) + "."
    return "Tradução para revisão individual."


EXACT_CORRECTIONS = {
    "my favorite food is japonese food": ("fix", "My favorite food is Japanese food.", "Japanese é escrito com a maiúscula e com a sequência -panese.", "Nacionalidades e idiomas começam com letra maiúscula em inglês."),
    "my favorite place is beach": ("fix", "My favorite place is the beach.", "Para falar da praia como lugar favorito, use the beach.", "Beach normalmente precisa de artigo nessa estrutura."),
    "my favorite place is at home": ("note", "My favorite place is home.", "A frase fica mais natural sem at.", "Home já funciona como ideia de lugar nessa frase."),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home.": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my favorite place is moutain": ("fix", "My favorite place is the mountains.", "A palavra correta é mountains, e a frase fica mais natural com the.", "Esse é um vocabulário comum para falar de lugares favoritos."),
    "my favorite sport is jiu-jitsu": ("ok", "My favorite sport is Jiu-Jitsu.", "", ""),
    "my favorite sport is bascketboll": ("fix", "My favorite sport is basketball.", "A palavra correta é basketball.", "Corrigir palavras frequentes ajuda o aluno a reutilizar a frase."),
    "my favorite sport is futeball": ("fix", "My favorite sport is football.", "Futeball é calque/erro de escrita. Use football.", "Sport vocabulary aparece muito em conversas simples."),
    "my favorite sport to whatch is american football nfl": ("fix", "My favorite sport to watch is American football (NFL).", "A palavra correta é watch. American fica com maiúscula.", "Watch é um verbo muito frequente; escrever corretamente evita confusão."),
    "my favorite day is sanday": ("fix", "My favorite day is Sunday.", "A palavra correta é Sunday.", "Dias da semana começam com maiúscula em inglês."),
    "my favorite language is spanish": ("note", "My favorite language is Spanish.", "Spanish começa com letra maiúscula.", "Idiomas sempre começam com maiúscula em inglês."),
    "my favorite language is portugues": ("fix", "My favorite language is Portuguese.", "A palavra correta é Portuguese.", "Idiomas sempre começam com maiúscula em inglês."),
    "my favorite make is mascara": ("fix", "My favorite makeup item is mascara.", "Make não funciona para maquiagem nessa frase. Use makeup item.", "Assim a frase fica clara e natural."),
    "my favorite hobby is travel": ("fix", "My favorite hobby is traveling.", "Depois de hobby is, use o substantivo/gerúndio traveling.", "Traveling funciona como atividade/hobby."),
    "my favorite exercise is walk": ("fix", "My favorite exercise is walking.", "Use walking como atividade.", "O gerúndio transforma o verbo em nome de atividade."),
    "my favorite pet is dog": ("fix", "My favorite pet is a dog.", "Dog no singular precisa de artigo.", "Substantivos contáveis no singular geralmente precisam de a/an."),
    "i am happy grateful and i am confident": ("fix", "I am happy and grateful, and I am confident.", "Faltou and entre happy e grateful.", "Quando há dois adjetivos juntos, and deixa a lista clara."),
    "as soon as i wake up i brush my teeth": ("note", "As soon as I wake up, I brush my teeth.", "Faltou vírgula depois da primeira parte.", "Quando As soon as inicia a frase, a vírgula melhora a leitura."),
    "as soon as i wake up, i have a break fast": ("fix", "As soon as I wake up, I have breakfast.", "Breakfast é uma palavra só, e a combinação natural é have breakfast.", "Have breakfast é uma expressão básica de rotina."),
    "as soon as i take a shower, i dry my hair": ("ok", "As soon as I take a shower, I dry my hair.", "", ""),
    "as soon as i finish practice english, i read a good book": ("fix", "As soon as I finish practicing English, I read a good book.", "Depois de finish, use o verbo com -ing: practicing.", "Finish + -ing é um padrão muito comum."),
    "as soon as i have a dinner, i watch a movie": ("fix", "As soon as I have dinner, I watch a movie.", "Use have dinner sem a.", "Meals normalmente não usam artigo nesse padrão."),
    "as soon i finish my work, i clear my tools": ("fix", "As soon as I finish my work, I clean my tools.", "Faltou as em As soon as, e clean é mais natural para ferramentas.", "A expressão completa é As soon as."),
    "as soon i wake up, i thank god": ("fix", "As soon as I wake up, I thank God.", "Faltou as em As soon as.", "A expressão completa precisa de as."),
    "as soon as i arrive in airport i do the chekin": ("fix", "As soon as I arrive at the airport, I check in.", "Use arrive at the airport e check in.", "Airport e check in são combinações naturais de viagem."),
    "as soon as i start watch my soccer team i feel angry": ("fix", "As soon as I start watching my soccer team, I feel angry.", "Depois de start, use watching. Também faltou a vírgula.", "Start + -ing aparece muito em rotinas e hábitos."),
    "as soon as i finish work, i pick-up my son at the school": ("fix", "As soon as I finish work, I pick up my son from school.", "Como verbo, use pick up sem hífen. From school fica mais natural.", "Phrasal verbs mudam quando viram substantivo ou verbo."),
    "as soon as i finish exercite, i drink water": ("fix", "As soon as I finish exercising, I drink water.", "Exercise é o verbo correto, e depois de finish use -ing.", "Finish exercising é a estrutura natural."),
    "as soon as i have coffe, i go to work": ("fix", "As soon as I have coffee, I go to work.", "A palavra correta é coffee.", "Coffee é vocabulário básico de rotina."),
    "as soon as i finish run, i check my phone": ("fix", "As soon as I finish running, I check my phone.", "Depois de finish, use running.", "Finish + -ing é uma regra muito útil."),
    "as soon as go to work, i thank god": ("fix", "As soon as I go to work, I thank God.", "Faltou o sujeito I depois de As soon as.", "Em inglês, a frase precisa de sujeito explícito."),
    "as soon as i finish dinner, i stay relax": ("fix", "As soon as I finish dinner, I relax.", "Stay relax não é natural. Use I relax ou I stay relaxed.", "Relax pode ser verbo direto: I relax."),
    "as soon as i wake up, i take a breakfast": ("fix", "As soon as I wake up, I have breakfast.", "Use have breakfast, sem a.", "Essa é a combinação natural para refeições."),
    "as soon as i arrivied in the office, i turn on my computer": ("fix", "As soon as I arrive at the office, I turn on my computer.", "Arrivied não existe. Use arrive at the office.", "Arrive at é comum para lugares específicos."),
    "as soon as i finish the walk outside, i'm fell tired": ("fix", "As soon as I finish my walk outside, I feel tired.", "Use I feel tired, não I'm fell tired.", "Feel já expressa o estado; não combine com am."),
    "as soon as i finish my work, i come back to my house": ("note", "As soon as I finish my work, I come back home.", "Come back home é mais natural que come back to my house.", "Home funciona como destino sem preposição nesse uso."),
    "as soon as i get home i take a long hot shower e then i have dinner": ("fix", "As soon as I get home, I take a long hot shower and then I have dinner.", "Troque e por and e use vírgula depois da primeira parte.", "Misturar português no meio da frase quebra a estrutura em inglês."),
    "as soon as finish work i take the road to get home": ("fix", "As soon as I finish work, I take the road to get home.", "Faltou o sujeito I.", "Em inglês, quase sempre precisamos explicitar o sujeito."),
    "i soon as i wake up i get out of the bed and take shower, then after bed dressed i start a new great day": ("fix", "As soon as I wake up, I get out of bed and take a shower. Then, after I get dressed, I start a great new day.", "A ordem correta é As soon as. Também ajuste take a shower e get dressed.", "Essa frase junta várias ações; separar em duas frases deixa tudo mais claro."),
    "as soon as i finish read my bible, i talk with you": ("fix", "As soon as I finish reading my Bible, I talk to you.", "Depois de finish, use reading. Prefira talk to you.", "Finish + -ing e talk to são padrões muito frequentes."),
    "as soon as i finish brush my teeth, i sleep": ("fix", "As soon as I finish brushing my teeth, I go to sleep.", "Depois de finish, use brushing. Go to sleep é mais natural.", "A expressão go to sleep fala da ação de dormir."),
    "as soon as i make the enterview, i call you": ("fix", "As soon as I do the interview, I call you.", "A palavra correta é interview; do the interview soa mais natural aqui.", "Algumas ações usam do em inglês, não make."),
    "as soon as i get home, i going to the gym": ("fix", "As soon as I get home, I'm going to the gym.", "Faltou am em I'm going.", "Going to precisa do verbo be: I am going to."),
    "as soon as ai finish my work, i try to study english": ("fix", "As soon as I finish my work, I try to study English.", "Ai deve ser I, e English começa com maiúscula.", "I e English são sempre maiúsculos."),
    "as soon as i receive my salary, i pay my bills": ("ok", "As soon as I receive my salary, I pay my bills.", "", ""),
    "as soon as i study english, i feel that i can to achieve fluency": ("fix", "As soon as I study English, I feel that I can achieve fluency.", "Depois de can, use o verbo base: achieve, não to achieve.", "Can + verbo base é uma regra central."),
    "my brother is one years old": ("fix", "My brother is one year old.", "Com one, use year no singular.", "One year old é uma expressão fixa."),
    "my mother is seventy eitgh years old": ("fix", "My mother is seventy-eight years old.", "A palavra correta é eight; em números compostos, use hífen.", "Números como seventy-eight e thirty-three usam hífen."),
    "my syster-in-law is fourty years old": ("fix", "My sister-in-law is forty years old.", "Use sister-in-law e forty.", "Family vocabulary e números são muito reutilizados."),
    "my soon is nineteen years old": ("fix", "My son is nineteen years old.", "A palavra correta é son.", "Son e soon têm significados diferentes."),
    "my nice is seven years old": ("fix", "My niece is seven years old.", "A palavra correta é niece.", "Niece é sobrinha; nice significa legal/gentil."),
    "i end up putting off my travel to the beach on weekend, because the weather was rainy": ("fix", "I ended up putting off my trip to the beach on the weekend because the weather was rainy.", "Use ended up no passado, trip para viagem curta e on the weekend.", "Essa estrutura conta algo que acabou acontecendo no passado."),
    "i ended up staying home office because in office the energy will be shut down": ("fix", "I ended up working from home because the power at the office was going to be shut off.", "Home office não funciona como verbo. Use working from home.", "Working from home é a expressão natural."),
    "i ended up bying a new dress because i went to a faschion party": ("fix", "I ended up buying a new dress because I went to a fashion party.", "As palavras corretas são buying e fashion.", "Essas palavras aparecem bastante em relatos pessoais."),
    "i am used to studing every day so activities don't bother me": ("fix", "I am used to studying every day, so activities don't bother me.", "Depois de used to, use -ing: studying.", "Be used to + -ing é a estrutura correta."),
    "i am used practing exercises every single day so go to the gym is a pleasure for me": ("fix", "I am used to practicing exercises every single day, so going to the gym is a pleasure for me.", "Faltou to em used to, e depois use practicing/going.", "Be used to + -ing é o padrão da atividade."),
    "i am used to listening music so this habit is part of my routine": ("fix", "I am used to listening to music, so this habit is part of my routine.", "Listen precisa de to antes de music.", "Listen to é uma combinação fixa."),
    "i am used to estudy english everyday day, so i keep i'm my mind everything that i learned": ("fix", "I am used to studying English every day, so I keep in my mind everything that I learned.", "Use studying, English com maiúscula e in my mind.", "Be used to + -ing e English maiúsculo são pontos centrais."),
    "i am used listen music when i'm going to run, so i fell more motivated to do it": ("fix", "I am used to listening to music when I'm going to run, so I feel more motivated to do it.", "Faltou to e listening to; fell deve ser feel.", "Feel e fell têm significados diferentes."),
    "i am used to take a shower before going to bed, so it's helps me sleep bete": ("fix", "I am used to taking a shower before going to bed, so it helps me sleep better.", "Use taking, it helps e better.", "Be used to + -ing e it helps são estruturas muito frequentes."),
    "as soon as i haver dinner, i'll call to my mother": ("fix", "As soon as I have dinner, I'll call my mother.", "Haver foi usado como calque do português. Em inglês, use have dinner e call my mother, sem to.", "Essa correção evita reforçar uma não-palavra e também fixa a combinação natural call + pessoa."),
    "as soon as i have lunch, i take a snap": ("fix", "As soon as I have lunch, I'll take a nap.", "Snap significa estalo ou foto rápida. Para cochilo, use nap.", "Trocar snap por nap muda completamente o sentido da frase."),
}


EXACT_CORRECTIONS.update({
    "my favorite sport is futeball": ("fix", "My favorite sport is soccer.", "A palavra correta é soccer/football. Para o contexto brasileiro, soccer deixa mais claro que é futebol.", "Escolher o termo mais natural para o público evita ambiguidade com futebol americano."),
    "my favorite make is mascara": ("fix", "My favorite makeup is mascara.", "Make não funciona como maquiagem nessa frase. Use makeup.", "Makeup é a palavra natural para falar de maquiagem."),
    "my favorite metalcore band is killswitch engage": ("note", "My favorite metalcore band is Killswitch Engage.", "Nome de banda deve manter a capitalização oficial.", "Nomes próprios precisam de maiúsculas para ficarem profissionais."),
    "my favorite day is wednesday": ("note", "My favorite day is Wednesday.", "Dias da semana começam com letra maiúscula em inglês.", "Esse padrão vale para todos os dias: Monday, Tuesday, Wednesday..."),
    "my favorite sport is running": ("note", "My favorite sport is running.", "A estrutura está correta; o ajuste é começar a frase com My em maiúsculo quando necessário.", "Capitalização correta deixa a escrita mais natural e cuidada."),
    "my favorite place is my home": ("ok", "My favorite place is my home.", "", ""),
    "my father is ninety one years old": ("note", "My father is ninety-one years old.", "Em números compostos, use hífen: ninety-one.", "O hífen deixa números compostos claros e corretos."),
    "as soon as i read a new word, i search its pronunciation and meaning": ("note", "As soon as I read a new word, I search its pronunciation and meaning.", "A frase está compreensível; o ajuste principal é padronizar I maiúsculo e pontuação.", "Manter a frase do aluno, quando ela faz sentido, reforça autonomia sem apagar a intenção."),
    "as soon as i get home, i take a quickly shower": ("fix", "As soon as I get home, I take a quick shower.", "Use quick shower, não quickly shower.", "Quick é adjetivo e descreve shower; quickly descreve uma ação."),
    "as soon as i get home, i make lunch and i will go to the gym": ("note", "As soon as I get home, I make lunch and then I go to the gym.", "A frase estava compreensível; then organiza melhor a sequência.", "Em frases de rotina, then ajuda a mostrar a ordem das ações."),
    "as soon as i buy something online, i regret": ("note", "As soon as I buy something online, I regret it.", "Regret precisa de objeto aqui: regret it.", "Alguns verbos precisam dizer claramente o que a pessoa sente ou faz."),
    "as soon as i get answser him, i report for you": ("fix", "As soon as I get an answer from him, I'll report back to you.", "A correção precisa ajustar a estrutura inteira, não só answer.", "Get an answer from someone e report back to someone são combinações naturais."),
    "as soon as i get reciving my money, i make payment for you": ("fix", "As soon as I receive my money, I'll pay you.", "Receive já expressa receber; get receiving não funciona.", "Usar o verbo certo deixa a frase curta e natural."),
    "as soon as ai learn french, i could change of the country": ("fix", "As soon as I learn French, I could move to another country.", "Change of the country não é inglês natural. Use move to another country.", "A frase precisa expressar mudança de país como ação: move to."),
    "as soon as i write my book, i lunch with you": ("fix", "As soon as I write my book, I'll have lunch with you.", "Lunch pode ser verbo, mas para iniciante o natural é have lunch.", "Have lunch é a forma mais comum e reutilizável."),
    "as soon as i have a doubt about english class, i ask for help to the teacher": ("fix", "As soon as I have a question about English class, I ask the teacher for help.", "Have a doubt é calque do português; prefira have a question. Também use ask the teacher for help.", "Essa correção troca uma frase traduzida literalmente por inglês natural."),
    "as soon as i finish my english study, i feel more confident to talk with friends": ("note", "As soon as I finish my English study, I feel more confident to talk with friends.", "English sempre começa com maiúscula.", "Idiomas são nomes próprios em inglês."),
    "as soon as i finish any meal, i brush my teeth": ("note", "As soon as I finish any meal, I brush my teeth.", "A frase está correta; o ajuste é escrever I sempre em maiúsculo.", "I é sempre maiúsculo em inglês."),
    "as soon as i get up, i will get up my kids too": ("fix", "As soon as I get up, I wake up my kids too.", "Para acordar outras pessoas, use wake up.", "Get up é levantar; wake up someone é acordar alguém."),
    "as soon as i hug my daughter, she tries to tickle me": ("note", "As soon as I hug my daughter, she tries to tickle me.", "A frase está correta; ajuste apenas o I maiúsculo.", "I sempre fica maiúsculo em inglês."),
    "i am used to going out with my family on weekends, so we have lot of fun": ("note", "I am used to going out with my family on weekends, so we have a lot of fun.", "Faltou a em a lot of.", "A lot of é uma expressão fixa."),
    "i am used to run twice a week so i am having good health": ("fix", "I am used to running twice a week, so I stay healthy.", "Depois de used to, use -ing. Stay healthy fica mais natural que having good health.", "Be used to + -ing é o padrão central da atividade."),
    "i am used to eat food without sugar so not eating sweets isn't a problem": ("fix", "I am used to eating food without sugar, so not eating sweets isn't a problem.", "Depois de used to, use eating.", "Be used to + -ing é o padrão central da atividade."),
    "i am used to get up early every day so i am having a long day": ("fix", "I am used to getting up early every day, so I have a long day.", "Depois de used to, use getting. Também prefira I have a long day.", "Be used to + -ing é o padrão central da atividade."),
    "i am used to speak out loud so i am speaking to crowd is easy": ("fix", "I am used to speaking out loud, so speaking to a crowd is easy.", "Depois de used to, use speaking. Também ajuste speaking to a crowd.", "A segunda parte precisa funcionar como sujeito: speaking to a crowd."),
    "i am used to wearing sun cream, so i don't get sunburn": ("note", "I am used to wearing sun cream, so I don't get sunburned.", "Sunburned funciona melhor como adjetivo para a pessoa.", "Esse ajuste deixa a frase mais natural."),
    "i'm used to reading book before sleep, so this is a habit for me": ("fix", "I'm used to reading a book before sleeping, so this is a habit for me.", "Use reading a book e before sleeping.", "O artigo a é necessário com book no singular."),
    "i'm used to preparing my breakfast in the morning, so my daily routines start after this": ("note", "I'm used to preparing my breakfast in the morning, so my daily routine starts after this.", "Routine no singular fica mais natural aqui.", "Ajustar singular/plural melhora a precisão da frase."),
    "i'm used to riding bike in the night, so finish my day with this activity is grateful for me": ("fix", "I'm used to riding a bike at night, so finishing my day with this activity is rewarding for me.", "Use riding a bike, at night e finishing. Grateful descreve pessoa, não atividade.", "A frase fica natural e mantém a intenção do aluno."),
    "i am used to eating salad so eat vegetables are frequent in my life": ("fix", "I am used to eating salad, so eating vegetables is frequent in my life.", "Use eating como sujeito e is no singular.", "Quando uma ação vira sujeito, o verbo em -ing ajuda muito."),
    "i'm used to spicy foods, so eating mexican food it's ok for me": ("fix", "I'm used to spicy foods, so eating Mexican food is ok for me.", "Mexican começa com maiúscula e não use it depois de eating Mexican food.", "Nacionalidades começam com maiúscula e a frase precisa de um sujeito claro."),
    "i'm used to heights, so i am not afraid of roller coaster": ("note", "I'm used to heights, so I am not afraid of roller coasters.", "Roller coasters no plural fica mais natural como categoria.", "O plural indica a ideia geral de montanhas-russas."),
    "i ended up sleeping during the movie, because it was so boring": ("note", "I ended up sleeping during the movie because it was so boring.", "A vírgula antes de because não é necessária nessa frase curta.", "Sem a vírgula, a frase fica mais natural."),
    "i end up sleeping during the movie, because it was so boring": ("note", "I ended up sleeping during the movie because it was so boring.", "Como a frase conta algo que aconteceu, use ended up no passado.", "Ended up é o padrão natural para relatar algo que acabou acontecendo."),
    "i ended up with this item because i forgot to change before expire": ("fix", "I ended up with this item because I forgot to change it before it expired.", "Faltou it depois de change e it expired no final.", "A frase precisa deixar claro o que venceu/expirou."),
    "i ended up going to the beach because the temperature was hot": ("note", "I ended up going to the beach because the weather was hot.", "Weather soa mais natural do que temperature nesse contexto.", "Falando do dia/tempo, weather é mais comum."),
    "no matter how i doing right i need to speak every day": ("fix", "No matter how I'm doing, I need to speak every day.", "A estrutura correta é how I'm doing.", "No matter how precisa de uma frase completa depois."),
})


EXACT_CORRECTIONS_NORM = {normalize_text(key): value for key, value in EXACT_CORRECTIONS.items()}


COMMON_REPLACEMENTS = [
    ("japonese", "Japanese"), ("moutain", "mountain"), ("bascketboll", "basketball"),
    ("whatch", "watch"), ("futeball", "soccer"), ("Sanday", "Sunday"),
    ("Manhwá", "Manhwa"), ("chekin", "check-in"), ("exercite", "exercise"),
    ("coffe", "coffee"), ("arrivied", "arrived"), ("enterview", "interview"),
    ("answser", "answer"), ("reciving", "receiving"), ("studing", "studying"),
    ("practing", "practicing"), ("estudy", "study"), ("bete", "better"),
    ("fourty", "forty"), ("syster", "sister"), ("eitgh", "eight"),
    ("bying", "buying"), ("faschion", "fashion"), ("portugues", "Portuguese"),
    ("spanish", "Spanish"),
]


def correct_phrase(activity: str, original: str) -> Phrase:
    normalized = normalize_text(original)
    if normalized in EXACT_CORRECTIONS_NORM:
        status, corrected, obs, why = EXACT_CORRECTIONS_NORM[normalized]
        corrected = tidy_sentence(corrected)
        return Phrase(original=original, activity=activity, timestamp=datetime.min, author_raw="", author_name="", status=status, corrected="" if status == "ok" else corrected, translation=translation_for(activity, corrected), observation=obs, why=why)

    corrected = tidy_sentence(original)
    observations = []
    for old, new in COMMON_REPLACEMENTS:
        if re.search(rf"\b{re.escape(old)}\b", corrected, flags=re.I):
            corrected = re.sub(rf"\b{re.escape(old)}\b", new, corrected, flags=re.I)
            observations.append(f"Ajuste de escrita: {old} -> {new}.")

    if activity == "favorite":
        corrected = re.sub(r"^my favorite", "My favorite", corrected, flags=re.I)
        corrected = re.sub(r"\bPlace\b", "place", corrected)
        corrected = re.sub(r"\bSport\b", "sport", corrected)
        corrected = re.sub(r"\bOrange Juice\b", "orange juice", corrected)
        corrected = re.sub(r"\bWine\b", "wine", corrected)
    elif activity == "iam":
        corrected = re.sub(r"^I'm\b", "I'm", corrected)
        corrected = re.sub(r"^I am\b", "I am", corrected, flags=re.I)
    elif activity == "as_soon":
        corrected = re.sub(r"^As soon I\b", "As soon as I", corrected, flags=re.I)
        corrected = re.sub(r"^As soon as ai\b", "As soon as I", corrected, flags=re.I)
        corrected = re.sub(r"^As soon as I Wake\b", "As soon as I wake", corrected)
        if re.match(r"^As soon as .+[^,] I ", corrected):
            corrected = re.sub(r"^(As soon as .+?)\s+(I .+)$", r"\1, \2", corrected)
            observations.append("Use vírgula depois da primeira parte com As soon as.")
    elif activity == "age":
        corrected = re.sub(r"(?<!-)\bone years old\b", "one year old", corrected, flags=re.I)
        corrected = re.sub(r"\bthirty four\b", "thirty-four", corrected, flags=re.I)
        corrected = re.sub(r"\bthirty three\b", "thirty-three", corrected, flags=re.I)
        corrected = re.sub(r"\bninety one\b", "ninety-one", corrected, flags=re.I)
    elif activity == "used_to":
        corrected = re.sub(r"\bI am used to run\b", "I am used to running", corrected, flags=re.I)
        corrected = re.sub(r"\bI am used to eat\b", "I am used to eating", corrected, flags=re.I)
        corrected = re.sub(r"\bI am used to get up\b", "I am used to getting up", corrected, flags=re.I)
        corrected = re.sub(r"\bI am used to speak\b", "I am used to speaking", corrected, flags=re.I)

    changed = corrected != tidy_sentence(original)
    status = "fix" if observations else ("note" if changed else "ok")
    obs = " ".join(observations) if observations else "A estrutura está boa; o ajuste deixa a frase mais natural e padronizada."
    why = "Pequenos ajustes de forma ajudam o aluno a reutilizar a frase em conversas reais."
    return Phrase(
        original=original,
        activity=activity,
        timestamp=datetime.min,
        author_raw="",
        author_name="",
        status=status,
        corrected="" if status == "ok" else corrected,
        translation=translation_for(activity, corrected),
        observation="" if status == "ok" else obs,
        why="" if status == "ok" else why,
    )


def build_phrases() -> list[Phrase]:
    messages = read_whatsapp_messages()
    ocr_results = ocr_screenshots()
    resolved_phones = resolve_phone_names(messages, ocr_results)
    phrases: list[Phrase] = []
    for message in messages:
        if message["author"].strip() == "Everyday Conversation":
            continue
        resolved_name = resolved_phones.get(message["author"], display_author(message["author"]))
        for candidate in split_into_candidate_phrases(message["text"]):
            activity = classify_activity(candidate)
            phrase = correct_phrase(activity, candidate)
            phrase.timestamp = message["timestamp"]
            phrase.author_raw = message["author"]
            phrase.author_name = resolved_name
            phrases.append(phrase)
    return phrases


def group_phrases(phrases: list[Phrase]) -> dict[str, list[StudentGroup]]:
    grouped: dict[tuple[str, str], StudentGroup] = {}
    for phrase in phrases:
        key = (phrase.activity, author_key(phrase.author_raw, phrase.author_name))
        if key not in grouped:
            grouped[key] = StudentGroup(key=key[1], name=phrase.author_name, activity=phrase.activity)
        grouped[key].phrases.append(phrase)
    by_activity: dict[str, list[StudentGroup]] = defaultdict(list)
    for group in grouped.values():
        by_activity[group.activity].append(group)
    for groups in by_activity.values():
        groups.sort(key=lambda g: normalize_text(g.name))
    return by_activity


def transcribe_ogg(path: Path) -> dict:
    out_path = TRANSCRIPT_DIR / f"{slug(path.stem, 80)}.json"
    if out_path.exists():
        cached = json.loads(out_path.read_text(encoding="utf-8"))
        if cached.get("words"):
            return cached
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = WhisperModel("base.en", device=device, compute_type=compute_type)
    start = time.time()
    segments, info = model.transcribe(str(path), language="en", word_timestamps=True)
    segment_data = []
    text_parts = []
    word_data = []
    for seg in segments:
        text_parts.append(seg.text)
        segment_words = []
        for word in seg.words or []:
            item = {
                "start": float(word.start),
                "end": float(word.end),
                "word": word.word.strip(),
                "probability": float(getattr(word, "probability", 0.0) or 0.0),
            }
            segment_words.append(item)
            word_data.append(item)
        segment_data.append({"start": seg.start, "end": seg.end, "text": seg.text, "words": segment_words})
    result = {
        "file": path.name,
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "text": " ".join(text_parts).strip(),
        "segments": segment_data,
        "words": word_data,
        "elapsed_seconds": time.time() - start,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def phrase_similarity_count(transcript: str, phrases: list[Phrase]) -> tuple[int, float]:
    scores = [token_score(transcript, phrase.original + " " + phrase_text(phrase)) for phrase in phrases]
    return sum(1 for s in scores if s >= 0.30), max(scores) if scores else 0.0


def audio_fingerprint(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nearest_group_seconds(group: StudentGroup, ogg_time: datetime | None) -> float | None:
    if not ogg_time or not group.phrases:
        return None
    return min(abs((phrase.timestamp - ogg_time).total_seconds()) for phrase in group.phrases)


def time_score_from_seconds(seconds: float | None) -> float:
    if seconds is None:
        return 0.0
    if seconds <= 300:
        return 0.55
    if seconds <= 900:
        return 0.30
    if seconds <= 3600:
        return 0.08
    return -0.20


def token_list(text: str) -> list[str]:
    return normalize_text(text).split()


def transcript_word_tokens(transcript: dict) -> list[dict]:
    tokens = []
    for word in transcript.get("words", []):
        parts = token_list(word.get("word", ""))
        for part in parts:
            tokens.append({"token": part, "start": float(word["start"]), "end": float(word["end"])})
    return tokens


def sequence_score(target: list[str], candidate: list[str]) -> float:
    if not target or not candidate:
        return 0.0
    overlap = len(set(target) & set(candidate)) / max(1, len(set(target)))
    ratio = difflib.SequenceMatcher(None, target, candidate).ratio()
    return (ratio * 0.62) + (overlap * 0.38)


def best_span_for_phrase(tokens: list[dict], phrase: Phrase, cursor: int) -> tuple[int, int, float] | None:
    target_options = [token_list(phrase.original)]
    if phrase.status != "ok" and phrase.corrected:
        target_options.append(token_list(phrase.corrected))
    remaining = len(tokens) - cursor
    if remaining <= 0:
        return None
    best: tuple[int, int, float] | None = None
    for target in target_options:
        if not target:
            continue
        min_len = max(2, int(len(target) * 0.55))
        max_len = min(remaining, max(min_len, int(len(target) * 1.75) + 4))
        max_start = min(len(tokens), cursor + max(8, len(target) + 8))
        for start in range(cursor, max_start):
            upper = min(len(tokens), start + max_len)
            for end in range(start + min_len, upper + 1):
                candidate = [item["token"] for item in tokens[start:end]]
                score = sequence_score(target, candidate)
                if best is None or score > best[2]:
                    best = (start, end, score)
    return best


def word_aligned_spans(transcript: dict, phrases: list[Phrase]) -> dict[int, dict]:
    tokens = transcript_word_tokens(transcript)
    if not tokens:
        return {}
    spans: dict[int, dict] = {}
    cursor = 0
    for index, phrase in enumerate(phrases, start=1):
        span = best_span_for_phrase(tokens, phrase, cursor)
        if not span:
            continue
        start_i, end_i, score = span
        if score < 0.43:
            continue
        start = max(0.0, tokens[start_i]["start"] - 0.18)
        end = min(float(transcript.get("duration") or tokens[end_i - 1]["end"]), tokens[end_i - 1]["end"] + 0.28)
        if end - start >= 0.45:
            spans[index] = {"start": start, "end": end, "score": round(score, 3), "method": "word"}
            cursor = end_i
    return spans


def segment_fallback_spans(transcript: dict, phrases: list[Phrase]) -> dict[int, dict]:
    spans = {}
    used_segments: set[int] = set()
    for phrase_index, phrase in enumerate(phrases, start=1):
        best = None
        for segment_index, segment in enumerate(transcript.get("segments", [])):
            if segment_index in used_segments:
                continue
            score = token_score(segment.get("text", ""), phrase.original + " " + phrase_text(phrase))
            if best is None or score > best[2]:
                best = (segment_index, segment, score)
        if best and best[2] >= 0.36:
            used_segments.add(best[0])
            segment = best[1]
            start = max(0.0, float(segment["start"]) - 0.18)
            end = min(float(transcript.get("duration") or segment["end"]), float(segment["end"]) + 0.28)
            if end - start >= 0.45:
                spans[phrase_index] = {"start": start, "end": end, "score": round(best[2], 3), "method": "segment"}
    return spans


def cut_student_clip(source: Path, target: Path, start: float, end: float) -> bool:
    if target.exists() and target.stat().st_size > 1000:
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            str(target),
        ],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and target.exists() and target.stat().st_size > 1000


def student_clip_name(group: StudentGroup, phrase_index: int, source: Path) -> str:
    return f"real_{activity_slug(group.activity)}_{slug(group.name, 24)}_{phrase_index:02d}_{slug(source.stem, 36)}.mp3"


def build_student_phrase_audios(copied: Path, transcript: dict, group: StudentGroup, fallback_audio: dict) -> list[dict]:
    spans = word_aligned_spans(transcript, group.phrases)
    fallback_spans = segment_fallback_spans(transcript, group.phrases)
    for index, span in fallback_spans.items():
        spans.setdefault(index, span)
    audios = []
    for phrase_index in sorted(spans):
        span = spans[phrase_index]
        clip_path = STUDENT_CLIP_DIR / student_clip_name(group, phrase_index, copied)
        if not cut_student_clip(copied, clip_path, span["start"], span["end"]):
            continue
        audios.append(
            {
                **fallback_audio,
                "path": rel(clip_path),
                "clip": True,
                "phrase_index": phrase_index,
                "clip_start": round(span["start"], 3),
                "clip_end": round(span["end"], 3),
                "clip_score": span["score"],
                "clip_method": span["method"],
            }
        )
    return audios


def audio_path_from_rel(path_text: str) -> Path:
    return ROOT / path_text.replace("/", os.sep)


def safe_audio_duration(path_text: str) -> float:
    try:
        path = audio_path_from_rel(path_text)
        if path.exists():
            return ffprobe_duration(path)
    except Exception:
        return 0.0
    return 0.0


def prune_duplicate_phrase_audios(audios: list[dict]) -> list[dict]:
    by_phrase: dict[int, list[dict]] = defaultdict(list)
    for audio in audios:
        by_phrase[int(audio.get("phrase_index", 1) or 1)].append(audio)
    result = []
    for phrase_index in sorted(by_phrase):
        items = by_phrase[phrase_index]
        if len(items) == 1:
            result.append(items[0])
            continue
        best = max(
            items,
            key=lambda item: (
                safe_audio_duration(item.get("path", "")),
                float(item.get("clip_score") or 0.0),
                float(item.get("score") or 0.0),
            ),
        )
        result.append(best)
    return result


def best_phrase_match_for_transcript(transcript_text: str, all_groups: list[StudentGroup]) -> dict:
    best = {"group": None, "index": 0, "score": 0.0}
    for group in all_groups:
        for index, phrase in enumerate(group.phrases, start=1):
            score = token_score(transcript_text, phrase.original + " " + phrase_text(phrase))
            if score > best["score"]:
                best = {"group": group, "index": index, "score": score}
    return best


def validate_audio_assignments(by_activity: dict[str, list[StudentGroup]]) -> list[dict]:
    all_groups = [group for groups in by_activity.values() for group in groups]
    issues = []
    for group in all_groups:
        group_text = " ".join(phrase.original + " " + phrase_text(phrase) for phrase in group.phrases)
        for audio in group.audios:
            transcript_text = audio.get("transcript", "")
            if not transcript_text:
                continue
            phrase_index = int(audio.get("phrase_index", 1) or 1)
            if phrase_index < 1 or phrase_index > len(group.phrases):
                continue
            assigned_phrase = group.phrases[phrase_index - 1]
            assigned_score = token_score(transcript_text, assigned_phrase.original + " " + phrase_text(assigned_phrase))
            assigned_group_score = token_score(transcript_text, group_text)
            best_group = None
            best_group_score = 0.0
            for candidate in all_groups:
                candidate_text = " ".join(phrase.original + " " + phrase_text(phrase) for phrase in candidate.phrases)
                score = token_score(transcript_text, candidate_text)
                if score > best_group_score:
                    best_group = candidate
                    best_group_score = score
            strong_elsewhere = best_group_score >= 0.34 and (best_group_score - assigned_group_score) >= 0.12 and best_group is not group
            weak_raw_audio = assigned_score < 0.18 and "student_submissions" in audio.get("path", "")
            if strong_elsewhere or weak_raw_audio:
                issues.append(
                    {
                        "audio": audio.get("file") or Path(audio.get("path", "")).name,
                        "assigned_activity": group.activity,
                        "assigned_student": group.name,
                        "assigned_phrase_index": phrase_index,
                        "assigned_score": round(assigned_score, 3),
                        "assigned_group_score": round(assigned_group_score, 3),
                        "best_activity": best_group.activity if best_group else "",
                        "best_student": best_group.name if best_group else "",
                        "best_group_score": round(best_group_score, 3),
                        "reason": "stronger transcript match elsewhere" if strong_elsewhere else "weak raw audio match",
                    }
                )
    report = OUT / "audio_assignment_warnings.json"
    if issues:
        report.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.environ.get("ALLOW_AUDIO_ASSIGNMENT_WARNINGS") != "1":
            raise RuntimeError(f"Audio assignment validation failed with {len(issues)} issue(s). See {report}")
    elif report.exists():
        report.unlink()
    return issues


def attach_student_audios(by_activity: dict[str, list[StudentGroup]]) -> list[dict]:
    all_groups = [group for groups in by_activity.values() for group in groups]
    unclassified = []
    seen_audio_hashes: set[str] = set()
    for ogg in sorted(INPUT_DIR.glob("*.ogg")):
        fingerprint = audio_fingerprint(ogg)
        if fingerprint in seen_audio_hashes:
            continue
        seen_audio_hashes.add(fingerprint)
        copied = STUDENT_AUDIO_DIR / ogg.name
        if not copied.exists():
            shutil.copy2(ogg, copied)
        transcript = transcribe_ogg(ogg)
        ogg_time = parse_ptt_datetime(ogg)
        best_group = None
        best_score = -1.0
        best_count = 0
        best_text_score = 0.0
        scored_groups = []
        for group in all_groups:
            count, text_score = phrase_similarity_count(transcript["text"], group.phrases)
            nearest = nearest_group_seconds(group, ogg_time)
            time_score = time_score_from_seconds(nearest)
            # Text is the primary signal. Timestamp proximity only helps choose
            # between already plausible text matches. This avoids assigning an
            # audio to a nearby card when the transcript clearly belongs to an
            # older/different card.
            # Keep transcript similarity dominant. Generic activities with many
            # repeated short phrases can otherwise win by count alone.
            score = (text_score * 3.0) + (min(count, 3) * 0.06) + min(time_score, 0.25)
            scored_groups.append(
                {
                    "group": group,
                    "count": count,
                    "text_score": text_score,
                    "nearest": nearest,
                    "score": score,
                }
            )
        strong_text = [
            item
            for item in scored_groups
            if item["text_score"] >= 0.34 or (item["count"] >= 3 and item["text_score"] >= 0.28)
        ]
        eligible = strong_text
        if not eligible:
            eligible = [
                item
                for item in scored_groups
                if item["nearest"] is not None and item["nearest"] <= 600 and item["text_score"] >= 0.20
            ]
        if not eligible:
            eligible = [
                item
                for item in scored_groups
                if item["nearest"] is not None and item["nearest"] <= 900 and item["text_score"] >= 0.18
            ]
        if not eligible:
            eligible = [
                item
                for item in scored_groups
                if item["text_score"] >= 0.24
            ]
        if not eligible:
            eligible = [
            item
            for item in scored_groups
            if item["nearest"] is not None and item["nearest"] <= 300 and item["text_score"] >= 0.12
            ]
        for item in eligible:
            if item["score"] > best_score:
                best_score = item["score"]
                best_group = item["group"]
                best_count = item["count"]
                best_text_score = item["text_score"]
        audio_data = {
            "file": copied.name,
            "path": rel(copied),
            "transcript": transcript["text"],
            "score": round(best_score, 3),
            "text_score": round(best_text_score, 3),
            "matched_phrases": best_count,
            "phrase_index": 1,
        }
        if best_group and (best_count >= 3 or best_text_score >= 0.34 or (best_score >= 0.70 and best_text_score >= 0.18)):
            phrase_scores = [
                (index, token_score(transcript["text"], phrase.original + " " + phrase_text(phrase)))
                for index, phrase in enumerate(best_group.phrases, start=1)
            ]
            strong_indices = [index for index, score in phrase_scores if score >= 0.30]
            if strong_indices:
                audio_data["phrase_index"] = min(strong_indices)
            elif phrase_scores:
                audio_data["phrase_index"] = max(phrase_scores, key=lambda item: item[1])[0]
            phrase_audios = build_student_phrase_audios(copied, transcript, best_group, audio_data)
            if phrase_audios:
                best_group.audios.extend(phrase_audios)
            else:
                best_group.audios.append(audio_data)
        else:
            unclassified.append(audio_data)
    for group in all_groups:
        group.audios = prune_duplicate_phrase_audios(group.audios)
    validate_audio_assignments(by_activity)
    return unclassified


def displayed_texts_for_words(phrase: Phrase) -> list[str]:
    if phrase.status == "ok":
        return [phrase.original]
    return [phrase.corrected]


def collect_targets(by_activity: dict[str, list[StudentGroup]]) -> tuple[list[dict], list[dict]]:
    sentence_targets = []
    word_map = {}
    for activity, groups in by_activity.items():
        for group in groups:
            for index, phrase in enumerate(group.phrases, start=1):
                text = phrase_text(phrase)
                sentence_id = f"s_{activity_slug(activity)}_{slug(group.name, 18)}_{index:02d}_{slug(text, 28)}"
                sentence_targets.append({"group": group.key, "activity": activity, "index": index, "text": text, "path": SENT_DIR / f"{sentence_id}.mp3"})
                for displayed in displayed_texts_for_words(phrase):
                    for word in words_in_text(displayed):
                        key = normalize_apostrophes(word).lower()
                        if key not in word_map:
                            word_id = f"w_{slug(key, 32)}"
                            word_map[key] = {"display": word, "key": key, "text": word_audio_text(word), "id": word_id, "path": WORD_DIR / f"{word_id}.mp3"}
    return sentence_targets, list(word_map.values())


def copy_cached(targets: list[dict], cache_dirs: list[Path]) -> int:
    copied = 0
    for target in targets:
        if target["path"].exists():
            continue
        cache_names = [target["path"].name]
        if "key" in target:
            clean = slug(target["key"], 32)
            cache_names.extend([f"word_{clean}.mp3", f"{clean}.mp3"])
        for cache_dir in cache_dirs:
            cached = next((cache_dir / name for name in cache_names if (cache_dir / name).exists()), None)
            if not cached:
                continue
            shutil.copy2(cached, target["path"])
            copied += 1
            break
    return copied


def remove_stale_audio_files(targets: list[dict], folder: Path) -> int:
    expected = {target["path"].name for target in targets}
    removed = 0
    for path in folder.glob("*.mp3"):
        if path.name not in expected:
            path.unlink()
            removed += 1
    return removed


def ffprobe_duration(path: Path) -> float:
    value = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    ).strip()
    return float(value)


def wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", str(mp3_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg failed")


def generate_one(model: Qwen3TTSModel, prompt, text: str, output: Path) -> None:
    wavs, sr = model.generate_voice_clone(text=normalize_apostrophes(text), language="English", voice_clone_prompt=prompt)
    audio = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
    temp = output.with_suffix(".temp.wav")
    sf.write(str(temp), audio, sr)
    wav_to_mp3(temp, output)
    temp.unlink(missing_ok=True)


def ensure_audio(by_activity: dict[str, list[StudentGroup]]) -> tuple[list[dict], list[dict]]:
    if not REF_AUDIO.exists():
        raise FileNotFoundError(f"Reference audio not found: {REF_AUDIO}")
    sentence_targets, word_targets = collect_targets(by_activity)
    removed_sentences = remove_stale_audio_files(sentence_targets, SENT_DIR)
    removed_words = remove_stale_audio_files(word_targets, WORD_DIR)
    copied_sentences = copy_cached(sentence_targets, CACHE_SENT_DIRS)
    copied_words = copy_cached(word_targets, CACHE_WORD_DIRS)
    missing = [target for target in sentence_targets + word_targets if not target["path"].exists()]
    limit = int(os.environ.get("MAX_AUDIO_PER_RUN", "0") or "0")
    batch = missing[:limit] if limit > 0 else missing

    print(f"Sentence targets: {len(sentence_targets)}", flush=True)
    print(f"Word targets: {len(word_targets)}", flush=True)
    print(f"Removed stale sentence audios: {removed_sentences}", flush=True)
    print(f"Removed stale word audios: {removed_words}", flush=True)
    print(f"Copied cached sentence audios: {copied_sentences}", flush=True)
    print(f"Copied cached word audios: {copied_words}", flush=True)
    print(f"Missing audio files: {len(missing)}", flush=True)
    if limit > 0 and len(batch) < len(missing):
        print(f"Batch limit: {limit}", flush=True)

    if os.environ.get("SKIP_AUDIO_GENERATION") == "1":
        print("Skipping missing audio generation by SKIP_AUDIO_GENERATION=1", flush=True)
        batch = []

    if batch:
        print("CUDA:", torch.cuda.is_available(), flush=True)
        if torch.cuda.is_available():
            print("GPU:", torch.cuda.get_device_name(0), flush=True)
        model = Qwen3TTSModel.from_pretrained(
            "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            device_map="cuda:0" if torch.cuda.is_available() else None,
            dtype=torch.bfloat16 if torch.cuda.is_available() else None,
        )
        prompt = model.create_voice_clone_prompt(ref_audio=str(REF_AUDIO), x_vector_only_mode=True)
        for n, target in enumerate(batch, start=1):
            print(f"[{n}/{len(batch)}] {target['text']}", flush=True)
            start = time.time()
            generate_one(model, prompt, target["text"], target["path"])
            print(f"    OK {target['path'].name} {ffprobe_duration(target['path']):.2f}s elapsed={time.time() - start:.2f}s", flush=True)

    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "activity": "multiatividades 06/05/2026",
                "voice": "Clone 16 YouTube",
                "reference_audio": str(REF_AUDIO),
                "sentence_count": len(sentence_targets),
                "word_count": len(word_targets),
                "sentences": [{**target, "path": str(target["path"])} for target in sentence_targets],
                "words": [{**target, "path": str(target["path"])} for target in word_targets],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return sentence_targets, word_targets


def status_counts(by_activity: dict[str, list[StudentGroup]]) -> dict:
    phrases = [phrase for groups in by_activity.values() for group in groups for phrase in group.phrases]
    students = {group.key for groups in by_activity.values() for group in groups}
    return {
        "students": len(students),
        "phrases": len(phrases),
        "ok": sum(1 for phrase in phrases if phrase.status == "ok"),
        "note": sum(1 for phrase in phrases if phrase.status == "note"),
        "fix": sum(1 for phrase in phrases if phrase.status == "fix"),
    }


def pill_html(css_class: str, icon: str, text: str) -> str:
    return f'<span class="pill {css_class}"><span class="mini-icon">{icon}</span>{escape(text)}</span>'


def metric_html(css_class: str, icon: str, value: int, label: str) -> str:
    return f"""
        <article class="metric-card {css_class}">
          <div class="metric-icon">{icon}</div>
          <strong>{value}</strong>
          <span>{escape(label)}</span>
        </article>"""


def audio_bank_html(word_targets: list[dict]) -> str:
    return "\n".join(f'<audio id="{escape(target["id"])}" preload="none" src="{escape(rel(target["path"]))}"></audio>' for target in word_targets)


def clickable_sentence(text: str, word_lookup: dict[str, dict], allowed_keys: set[str] | None = None) -> str:
    parts = []
    last = 0
    for match in INLINE_WORD_RE.finditer(text):
        parts.append(escape(text[last : match.start()]))
        word = match.group(0)
        key = normalize_apostrophes(word).lower()
        target = word_lookup.get(key)
        if target and (allowed_keys is None or key in allowed_keys):
            parts.append(
                f'<span class="audio-word" role="button" tabindex="0" data-audio="{escape(target["id"])}" '
                f'title="Ouvir {escape(word)}" aria-label="Ouvir {escape(word)}">{escape(word)}</span>'
            )
        else:
            parts.append(escape(word))
        last = match.end()
    parts.append(escape(text[last:]))
    return "".join(parts)


def phrase_html(group: StudentGroup, phrase: Phrase, index: int, sentence_lookup: dict, word_lookup: dict) -> str:
    status = phrase.status
    sentence_target = sentence_lookup[(phrase.activity, group.key, index)]
    if status == "ok":
        original_sentence = clickable_sentence(phrase.original, word_lookup)
    else:
        original_sentence = escape(phrase.original)
    lines = [
        f"""
          <div class="line-row">
            <div class="label">Original</div>
            <div class="sentence">{original_sentence}</div>
          </div>"""
    ]
    side_dots = ['<div class="side-dot">&#9679;</div>']
    if status != "ok":
        lines.append(
            f"""
          <div class="line-row">
            <div class="label recommended">Recomendada</div>
            <div class="sentence corrected">{clickable_sentence(phrase.corrected, word_lookup)}</div>
          </div>"""
        )
        side_dots.append('<div class="side-dot recommended">&#9733;</div>')
    lines.append(
        f"""
          <div class="line-row">
            <div class="label">Tradução</div>
            <div class="sentence translation">{escape(phrase.translation)}</div>
          </div>"""
    )
    side_dots.append('<div class="side-dot translation">&#9633;</div>')
    if sentence_target["path"].exists():
        lines.append(
            f"""
          <div class="audio-row">
            <div class="label">Áudio modelo</div>
            <audio controls preload="none" src="{escape(rel(sentence_target["path"]))}"></audio>
          </div>"""
        )
    real_audio_panel = phrase_student_audio_panel(group, index)
    if real_audio_panel:
        lines.append(real_audio_panel)
    explain = ""
    if status != "ok":
        explain = f"""
        <div class="explain">
          <div class="explain-piece">
            <div class="explain-icon">!</div>
            <div><strong>Observação:</strong>{escape(phrase.observation)}</div>
          </div>
          <div class="explain-piece">
            <div class="explain-icon">i</div>
            <div><strong>Por que isso importa:</strong>{escape(phrase.why)}</div>
          </div>
        </div>"""
    status_text = STATUS[status]["icon"] if status == "ok" else STATUS[status]["label"]
    return f"""
      <article class="phrase-card {status}" data-status="{status}">
        <div class="phrase-side">
          <div class="phrase-index">{index}</div>
          {"".join(side_dots)}
        </div>
        <div class="phrase-main">
          <h4 class="phrase-title">Frase {index}</h4>
          <div class="phrase-lines">{"".join(lines)}</div>
        </div>
        <div class="status-badge">{status_text}</div>
        {explain}
      </article>"""


def phrase_student_audio_panel(group: StudentGroup, index: int) -> str:
    audios = [audio for audio in group.audios if int(audio.get("phrase_index", 1) or 1) == index]
    if not audios:
        return ""
    panels = []
    for audio in audios:
        panels.append(
            f"""
          <div class="audio-row student-audio-row">
            <div class="label">Áudio real</div>
        <audio controls preload="none" src="{escape(audio["path"])}"></audio>
      </div>"""
        )
    return "\n".join(panels)


def student_html(group: StudentGroup, sentence_lookup: dict, word_lookup: dict) -> str:
    counts = {
        "ok": sum(1 for phrase in group.phrases if phrase.status == "ok"),
        "note": sum(1 for phrase in group.phrases if phrase.status == "note"),
        "fix": sum(1 for phrase in group.phrases if phrase.status == "fix"),
    }
    phrase_markup = "\n".join(phrase_html(group, phrase, index, sentence_lookup, word_lookup) for index, phrase in enumerate(group.phrases, start=1))
    ok_text = f'{counts["ok"]} {plural(counts["ok"], STATUS["ok"]["short"], STATUS["ok"]["short_plural"])}'
    note_text = f'{counts["note"]} {plural(counts["note"], STATUS["note"]["short"], STATUS["note"]["short_plural"])}'
    fix_text = f'{counts["fix"]} {plural(counts["fix"], STATUS["fix"]["short"], STATUS["fix"]["short_plural"])}'
    phone_last4 = sorted(
        {
            re.sub(r"\D", "", phrase.author_raw)[-4:]
            for phrase in group.phrases
            if phrase.author_raw.strip().startswith("+") and re.sub(r"\D", "", phrase.author_raw)
        }
    )
    search_terms = " ".join([group.name, normalize_text(group.name), group.key, *phone_last4])
    return f"""
    <article class="student-card" data-open="false" data-has-issues="{str(counts["note"] + counts["fix"] > 0).lower()}" data-student="{escape(normalize_text(group.name))}" data-student-name="{escape(group.name)}" data-search="{escape(normalize_text(search_terms))}">
      <header class="student-head" role="button" tabindex="0" aria-expanded="false">
        <div class="student-id">
          <div class="student-avatar">&#9679;</div>
          <h3>{escape(group.name)}</h3>
        </div>
        <div class="student-stats">
          {pill_html("ok", "&check;", ok_text)}
          {pill_html("note", "!", note_text)}
          {pill_html("fix", "&times;", fix_text)}
          <span class="student-toggle" aria-hidden="true">▼</span>
        </div>
      </header>
      <div class="phrases">
        {phrase_markup}
      </div>
    </article>"""


def activity_panels_html(by_activity: dict[str, list[StudentGroup]], sentence_lookup: dict, word_lookup: dict) -> tuple[str, str]:
    panels = []
    tabs = []
    ordered = sorted(by_activity.items(), key=lambda item: ACTIVITIES[item[0]]["order"])
    for idx, (activity, groups) in enumerate(ordered):
        phrase_count = sum(len(group.phrases) for group in groups)
        student_count = len(groups)
        tab_count_text = f"{student_count} {'aluno' if student_count == 1 else 'alunos'}"
        title = ACTIVITIES[activity]["title"]
        dom_activity = activity_slug(activity)
        active = " active" if idx == 0 else ""
        tabs.append(
            f'<button class="tab-button{active}" type="button" data-tab="{escape(dom_activity)}">{escape(title)}<span class="tab-count">{escape(tab_count_text)}</span></button>'
        )
        students_markup = "\n".join(student_html(group, sentence_lookup, word_lookup) for group in groups)
        panels.append(
            f"""
    <section class="activity-panel{active}" data-activity="{escape(dom_activity)}">
      <div class="section-title">
        <div class="section-icon">&#9646;</div>
        <div>
          <h2>{escape(title)}</h2>
          <p class="activity-summary">{len(groups)} alunos | {phrase_count} frases | Modelo: {escape(ACTIVITIES[activity]["model"])}</p>
        </div>
      </div>
      <div class="activity-controls">
        <button class="activity-action expand-all" type="button">▾ Expandir todos</button>
        <button class="activity-action collapse-all" type="button">▴ Recolher todos</button>
        <button class="activity-action issue-filter" type="button" aria-pressed="false">Mostrar só os com correção</button>
      </div>
      <div class="student-list">
        {students_markup}
      </div>
    </section>"""
        )
    return "\n".join(tabs), "\n".join(panels)


def unclassified_html(items: list[dict]) -> str:
    if not items:
        return ""
    cards = []
    for item in items:
        cards.append(
            f"""
      <article class="unclassified-audio">
        <strong>{escape(item["file"])}</strong>
        <audio controls preload="none" src="{escape(item["path"])}"></audio>
      </article>"""
        )
    return f"""
    <section class="lesson-section">
      <div class="section-title">
        <div class="section-icon">?</div>
        <div>
          <h2>Áudios não classificados</h2>
          <p>Arquivos reais que foram transcritos, mas não bateram com segurança com uma atividade específica.</p>
        </div>
      </div>
      <div class="unclassified-list">
        {"".join(cards)}
      </div>
    </section>"""


def render(by_activity: dict[str, list[StudentGroup]], sentence_targets: list[dict], word_targets: list[dict], unclassified: list[dict]) -> None:
    counts = status_counts(by_activity)
    sentence_lookup = {(target["activity"], target["group"], target["index"]): target for target in sentence_targets}
    existing_word_targets = [target for target in word_targets if target["path"].exists()]
    word_lookup = {target["key"]: target for target in existing_word_targets}
    tabs, panels = activity_panels_html(by_activity, sentence_lookup, word_lookup)
    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Relatório Multiatividades com Áudio - 06/05/2026</title>
  <style>{CSS}</style>
</head>
<body>
  <main class="page">
    <section class="hero-shell">
      <img class="brand-logo" src="assets_relatorios/logo_everyday_conversation.png" alt="Everyday Conversation" />
      <div class="hero-card">
        <div class="hero-asset-wrap">
          <img class="hero-asset" src="assets_relatorios/hero_books_plant_chat.png" alt="" />
        </div>
        <div>
          <div class="eyebrow">Conversa do dia a dia</div>
          <h1>Correção guiada<br>multiatividades</h1>
          <p>Rodada: <strong>06/05/2026</strong> com atividades em sequência, busca por aluno e áudios reais associados.</p>
          <p>As palavras clicáveis aparecem apenas em frases corretas ou nas versões recomendadas, evitando reforçar erros de pronúncia.</p>
        </div>
      </div>
      <aside class="metrics-grid multi-metrics" aria-label="Resumo global">
        {metric_html("blue", "&#9679;", counts["phrases"], "frases analisadas")}
        {metric_html("purple", "&#9679;&#9679;", counts["students"], "alunos participantes")}
        {metric_html("green", "&check;", counts["ok"], "tudo certo")}
        {metric_html("orange", "!", counts["note"], "ajuste leve")}
        {metric_html("red", "&times;", counts["fix"], "precisa corrigir")}
      </aside>
    </section>

    <section class="search-panel" aria-label="Busca global por aluno">
      <div>
        <label for="studentSearch">Buscar aluno</label>
        <input id="studentSearch" class="search-input" type="search" placeholder="Digite seu nome ou os 4 últimos algarismos do seu telefone" autocomplete="off" />
      </div>
      <div class="search-meta" id="searchMeta">Mostrando todos os alunos</div>
    </section>

    <section class="legend-bar" aria-label="Legenda">
      <div class="legend-left">
        {pill_html("ok", "&check;", "Tudo certo")}
        {pill_html("note", "!", "Ajuste leve")}
        {pill_html("fix", "&times;", "Precisa corrigir")}
        {pill_html("info", "&#9679;", "Áudio modelo incluído")}
      </div>
      {pill_html("review", "&#9678;", "Revisão por nomes reais")}
    </section>

    <nav class="tabs-bar" aria-label="Atividades">
      {tabs}
    </nav>

    {panels}

    {unclassified_html(unclassified)}

    <div class="audio-bank">
      {audio_bank_html(existing_word_targets)}
    </div>
    <script>
      function playWordAudio(id) {{
        const audio = document.getElementById(id);
        if (!audio) return;
        audio.currentTime = 0;
        audio.play();
      }}
      document.addEventListener('click', event => {{
        const item = event.target.closest('.audio-word[data-audio]');
        if (item) playWordAudio(item.dataset.audio);
      }});
      document.addEventListener('keydown', event => {{
        const item = event.target.closest('.audio-word[data-audio]');
        if (!item || (event.key !== 'Enter' && event.key !== ' ')) return;
        event.preventDefault();
        playWordAudio(item.dataset.audio);
      }});
      const search = document.getElementById('studentSearch');
      const meta = document.getElementById('searchMeta');
      const tabs = Array.from(document.querySelectorAll('.tab-button'));
      const panels = Array.from(document.querySelectorAll('.activity-panel'));
      function normalizeQuery(value) {{
        return (value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
      }}
      function isStackedMode() {{
        return true;
      }}
      function setActive(tabName, scrollToPanel = false) {{
        tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.tab === tabName));
        panels.forEach(panel => panel.classList.toggle('active', panel.dataset.activity === tabName));
        if (scrollToPanel) {{
          const panel = panels.find(item => item.dataset.activity === tabName);
          if (panel) panel.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        }}
      }}
      function setCardOpen(card, open) {{
        card.dataset.open = open ? 'true' : 'false';
        const head = card.querySelector('.student-head');
        const toggle = card.querySelector('.student-toggle');
        if (head) head.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (toggle) toggle.textContent = open ? '▲' : '▼';
      }}
      function visibleCards(panel) {{
        return Array.from(panel.querySelectorAll('.student-card')).filter(card =>
          card.dataset.hidden !== 'true' && card.dataset.filteredCorrect !== 'true'
        );
      }}
      function applySearch() {{
        const query = normalizeQuery(search.value);
        document.body.classList.toggle('searching', !!query);
        let total = 0;
        let firstMatch = null;
        panels.forEach(panel => {{
          let panelMatches = 0;
          panel.querySelectorAll('.student-card').forEach(card => {{
            const name = normalizeQuery(card.dataset.studentName || '');
            const normalized = normalizeQuery(card.dataset.student || '');
            const searchBlob = normalizeQuery(card.dataset.search || '');
            const visible = !query || name.includes(query) || normalized.includes(query) || searchBlob.includes(query);
            card.dataset.hidden = visible ? 'false' : 'true';
            if (query) setCardOpen(card, visible);
            else setCardOpen(card, false);
            if (visible) {{
              panelMatches += 1;
              total += 1;
            }}
          }});
          panel.dataset.searchMatch = panelMatches > 0 ? 'true' : 'false';
          const tab = tabs.find(item => item.dataset.tab === panel.dataset.activity);
          if (tab) tab.classList.toggle('has-match', !!query && panelMatches > 0);
          if (!firstMatch && panelMatches > 0) firstMatch = panel.dataset.activity;
        }});
        meta.textContent = query ? `${{total}} resultado(s) para "${{search.value}}"` : 'Mostrando todos os alunos';
        if (query && firstMatch) {{
          setActive(firstMatch);
        }}
      }}
      tabs.forEach(tab => tab.addEventListener('click', () => setActive(tab.dataset.tab, isStackedMode())));
      if ('IntersectionObserver' in window) {{
        const observer = new IntersectionObserver(entries => {{
          const visible = entries
            .filter(entry => entry.isIntersecting)
            .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
          if (visible) setActive(visible.target.dataset.activity);
        }}, {{ rootMargin: '-18% 0px -66% 0px', threshold: [0.12, 0.28, 0.45] }});
        panels.forEach(panel => observer.observe(panel));
      }}
      document.querySelectorAll('.student-head').forEach(head => {{
        head.addEventListener('click', event => {{
          if (event.target.closest('audio')) return;
          const card = head.closest('.student-card');
          setCardOpen(card, card.dataset.open !== 'true');
        }});
        head.addEventListener('keydown', event => {{
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          const card = head.closest('.student-card');
          setCardOpen(card, card.dataset.open !== 'true');
        }});
      }});
      document.querySelectorAll('.activity-panel').forEach(panel => {{
        const expand = panel.querySelector('.expand-all');
        const collapse = panel.querySelector('.collapse-all');
        const issueFilter = panel.querySelector('.issue-filter');
        if (expand) expand.addEventListener('click', () => visibleCards(panel).forEach(card => setCardOpen(card, true)));
        if (collapse) collapse.addEventListener('click', () => visibleCards(panel).forEach(card => setCardOpen(card, false)));
        if (issueFilter) issueFilter.addEventListener('click', () => {{
          const active = issueFilter.getAttribute('aria-pressed') !== 'true';
          issueFilter.setAttribute('aria-pressed', active ? 'true' : 'false');
          issueFilter.classList.toggle('active', active);
          panel.querySelectorAll('.student-card').forEach(card => {{
            card.dataset.filteredCorrect = active && card.dataset.hasIssues !== 'true' ? 'true' : 'false';
          }});
        }});
      }});
      search.addEventListener('input', applySearch);
      applySearch();
    </script>
    <p class="footer">Relatório local para revisão no Opus 4.7 antes de qualquer publicação.</p>
  </main>
</body>
</html>"""
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print("HTML:", OUTPUT_HTML, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-transcribe", action="store_true", help="Skip OGG transcription and matching.")
    args = parser.parse_args()
    start = time.time()
    phrases = build_phrases()
    by_activity = group_phrases(phrases)
    unclassified = [] if args.no_transcribe else attach_student_audios(by_activity)
    sentence_targets, word_targets = ensure_audio(by_activity)
    render(by_activity, sentence_targets, word_targets, unclassified)
    print(f"Done in {time.time() - start:.2f}s", flush=True)
if __name__ == "__main__":
    main()
