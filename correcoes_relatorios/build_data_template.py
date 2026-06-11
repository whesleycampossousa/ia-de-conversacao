from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data_YYYY_MM_DD_corrections.jsonl"


def row(student, raw_author, time, activity, status, original, corrected, translation, observation="", why=""):
    return {
        "student": student,
        "raw_author": raw_author,
        "time": time,
        "activity": activity,
        "status": status,
        "original": original,
        "corrected": corrected,
        "translation": translation,
        "observation": observation,
        "why": why,
    }


ROWS = [
    # Troque estes exemplos pelas respostas do dia.
    row(
        "Aluno Exemplo",
        "Cliente Aluno Exemplo",
        "8:00 AM",
        "activity_slug",
        "fix",
        "Original sentence from the student.",
        "Corrected sentence for the student.",
        "Tradução natural em português.",
        "Explique exatamente o que mudou. Se uma palavra do aluno estava correta, preserve-a; se sugerir outra, diga que a original também estava correta.",
        "Explique por que a mudança importa para o aluno reutilizar a estrutura.",
    ),
]


def main() -> None:
    with OUT.open("w", encoding="utf-8") as fh:
        for item in ROWS:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Wrote {len(ROWS)} rows to {OUT}")


if __name__ == "__main__":
    main()
