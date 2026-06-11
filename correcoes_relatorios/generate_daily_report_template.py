from __future__ import annotations

import importlib.util
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "generate_base_clone16_audio_report.py"
spec = importlib.util.spec_from_file_location("daily_report_base", BASE_PATH)
base = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = base
spec.loader.exec_module(base)


REPORT_SLUG = "YYYY_MM_DD"
INPUT_DIR = Path.home() / "Downloads" / "PASTA_DO_DIA"

base.INPUT_DIR = INPUT_DIR
base.DATA_PATH = ROOT / f"data_{REPORT_SLUG}_corrections.jsonl"
base.OUT = ROOT / f"relatorio_{REPORT_SLUG}_clone16_audio"
base.AUDIO_DIR = base.OUT / "audio"
base.SENT_DIR = base.AUDIO_DIR / "sentences"
base.WORD_DIR = base.AUDIO_DIR / "words"
base.STUDENT_AUDIO_DIR = base.AUDIO_DIR / "student_submissions"
base.STUDENT_CLIP_DIR = base.AUDIO_DIR / "student_sentence_clips"
base.TRANSCRIPT_DIR = base.OUT / "transcripts"
base.OUTPUT_HTML = ROOT / f"relatorio_correcao_{REPORT_SLUG}_com_audio_clone16.html"
base.MANIFEST_PATH = base.OUT / f"manifest_{REPORT_SLUG}_clone16_audio.json"
base.OCR_RESULTS_PATH = base.OUT / f"ocr_results_{REPORT_SLUG}.json"
base.NAME_MAP_PATH = base.OUT / f"resolved_author_names_{REPORT_SLUG}.json"
base.PHONE_TEMPLATE_PATH = base.OUT / f"phone_to_name_template_{REPORT_SLUG}.json"

base.ACTIVITIES = {
    "activity_slug": {
        "title": "1ª Atividade - Nome da atividade",
        "model": "Modelo curto da estrutura",
        "order": 1,
        "question": "Pergunta em português para contexto interno.",
        "question_en": "Question in English shown in the report.",
        "question_pt": "Pergunta em português exibida no relatório.",
    },
}


def ts(value: str) -> datetime:
    # Ajuste a data do relatório aqui.
    return datetime.strptime(f"DD/MM/YYYY {value}", "%d/%m/%Y %I:%M %p")


base.ts = ts


# Mapear apenas áudios seguros. Se houver dúvida, deixe fora para não misturar aluno/card.
STRICT_AUDIO_MAP = {
    # "WhatsApp Ptt 2026-06-12 at 8.00.00 AM.ogg": [("activity_slug", "Aluno Exemplo")],
}


def attach_student_audios_daily(by_activity: dict) -> list[dict]:
    multi = base.base
    groups = {
        (activity, group.name): group
        for activity, activity_groups in by_activity.items()
        for group in activity_groups
    }
    unclassified: list[dict] = []
    seen: set[str] = set()
    for ogg in sorted(multi.INPUT_DIR.glob("*.ogg")):
        fingerprint = multi.audio_fingerprint(ogg)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        copied = multi.STUDENT_AUDIO_DIR / ogg.name
        if not copied.exists() or copied.stat().st_size != ogg.stat().st_size:
            shutil.copy2(ogg, copied)
        transcript = multi.transcribe_ogg(ogg)
        base_audio = {
            "file": copied.name,
            "path": multi.rel(copied),
            "transcript": transcript["text"],
            "score": 1,
            "text_score": 1,
            "matched_phrases": 1,
            "phrase_index": 1,
        }
        targets = STRICT_AUDIO_MAP.get(ogg.name, [])
        if not targets:
            unclassified.append(dict(base_audio))
            continue
        for target in targets:
            group = groups.get(target)
            if group is None:
                unclassified.append(dict(base_audio))
                continue
            phrase_audios = multi.build_student_phrase_audios(copied, transcript, group, dict(base_audio))
            if phrase_audios:
                group.audios.extend(phrase_audios)
            else:
                group.audios.append(dict(base_audio))
    return unclassified


base.attach_student_audios_25 = attach_student_audios_daily


if __name__ == "__main__":
    base.main()
    html = base.OUTPUT_HTML.read_text(encoding="utf-8")
    html = html.replace("04/06/2026", "DD/MM/YYYY")
    base.OUTPUT_HTML.write_text(html, encoding="utf-8")
    base.validate_report_25()
