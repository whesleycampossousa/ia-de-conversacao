#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extract all English phrases from lessons_db.json for TTS generation.

Usage:
    python scripts/extract_lesson_phrases.py

Output:
    scripts/phrases_to_generate.json - All phrases with metadata

This script extracts:
- Welcome messages (33)
- Layer instructions (~231)
- Options (~924)
- Practice prompts (~231)
- Conclusions (33)

Total: ~1,452 phrases
"""

import json
import os
from pathlib import Path
from collections import Counter


def extract_phrases(lessons_db_path: str) -> list:
    """Extract all English phrases from lessons database."""

    with open(lessons_db_path, 'r', encoding='utf-8') as f:
        lessons = json.load(f)

    phrases = []
    stats = Counter()

    for lesson_id, lesson in lessons.items():
        # Welcome message
        if 'welcome' in lesson and 'en' in lesson['welcome']:
            phrases.append({
                "id": f"{lesson_id}_welcome",
                "text": lesson['welcome']['en'],
                "type": "welcome",
                "lesson": lesson_id,
                "layer": None
            })
            stats['welcome'] += 1

        # Layers
        if 'layers' in lesson:
            for layer in lesson['layers']:
                layer_id = layer.get('id', 0)

                # Instruction
                if 'instruction' in layer and 'en' in layer['instruction']:
                    phrases.append({
                        "id": f"{lesson_id}_layer{layer_id}_instruction",
                        "text": layer['instruction']['en'],
                        "type": "instruction",
                        "lesson": lesson_id,
                        "layer": layer_id
                    })
                    stats['instruction'] += 1

                # Options
                if 'options' in layer:
                    for idx, opt in enumerate(layer['options']):
                        if isinstance(opt, dict) and 'en' in opt:
                            phrases.append({
                                "id": f"{lesson_id}_layer{layer_id}_opt{idx}",
                                "text": opt['en'],
                                "type": "option",
                                "lesson": lesson_id,
                                "layer": layer_id
                            })
                            stats['option'] += 1

                # Practice prompt
                if 'practice_prompt' in layer and 'en' in layer['practice_prompt']:
                    phrases.append({
                        "id": f"{lesson_id}_layer{layer_id}_practice",
                        "text": layer['practice_prompt']['en'],
                        "type": "practice_prompt",
                        "lesson": lesson_id,
                        "layer": layer_id
                    })
                    stats['practice_prompt'] += 1

                # Feedback templates (success, retry, redirect)
                if 'feedback' in layer:
                    for fb_type in ['success', 'retry', 'redirect']:
                        fb = layer['feedback'].get(fb_type, {})
                        if 'en' in fb:
                            phrases.append({
                                "id": f"{lesson_id}_layer{layer_id}_fb_{fb_type}",
                                "text": fb['en'],
                                "type": f"feedback_{fb_type}",
                                "lesson": lesson_id,
                                "layer": layer_id
                            })
                            stats[f'feedback_{fb_type}'] += 1

        # Conclusion
        if 'conclusion' in lesson and 'en' in lesson['conclusion']:
            phrases.append({
                "id": f"{lesson_id}_conclusion",
                "text": lesson['conclusion']['en'],
                "type": "conclusion",
                "lesson": lesson_id,
                "layer": None
            })
            stats['conclusion'] += 1

    return phrases, stats


def main():
    # Change to project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    print("=" * 60)
    print("  LESSON PHRASE EXTRACTOR")
    print("=" * 60)

    lessons_db_path = "lessons_db.json"
    output_path = "scripts/phrases_to_generate.json"

    if not os.path.exists(lessons_db_path):
        print(f"\n  [ERROR] File not found: {lessons_db_path}")
        print("  Make sure you're running from the project root.")
        return

    print(f"\n  Input: {lessons_db_path}")
    print(f"  Output: {output_path}")
    print("=" * 60 + "\n")

    # Extract phrases
    print("[1/2] Extracting phrases from lessons database...")
    phrases, stats = extract_phrases(lessons_db_path)

    # Print statistics
    print("\n  Statistics by type:")
    print("  " + "-" * 40)
    for phrase_type, count in stats.items():
        print(f"    {phrase_type:20s}: {count:4d}")
    print("  " + "-" * 40)
    print(f"    {'TOTAL':20s}: {len(phrases):4d}")

    # Get unique lessons
    lessons = set(p['lesson'] for p in phrases)
    print(f"\n  Lessons covered: {len(lessons)}")

    # Save to JSON
    print(f"\n[2/2] Saving to {output_path}...")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(phrases, f, indent=2, ensure_ascii=False)

    print(f"  [OK] Saved {len(phrases)} phrases")

    # Create a summary file for quick reference
    summary_path = "scripts/phrases_summary.txt"
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("LESSON PHRASES SUMMARY\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Total phrases: {len(phrases)}\n")
        f.write(f"Total lessons: {len(lessons)}\n\n")
        f.write("By type:\n")
        for phrase_type, count in stats.items():
            f.write(f"  - {phrase_type}: {count}\n")
        f.write("\n\nSample phrases:\n")
        f.write("-" * 60 + "\n")
        for i, p in enumerate(phrases[:10]):
            f.write(f"\n[{p['id']}]\n")
            f.write(f"  Type: {p['type']}\n")
            f.write(f"  Text: {p['text'][:80]}{'...' if len(p['text']) > 80 else ''}\n")

    print(f"  [OK] Summary saved to {summary_path}")

    print("\n" + "=" * 60)
    print("  EXTRACTION COMPLETE!")
    print("=" * 60)
    print(f"\n  Total phrases extracted: {len(phrases)}")
    print(f"\n  Next steps:")
    print("  1. Run scripts/download_voice_reference.py")
    print("  2. Transcribe the voice reference audio")
    print("  3. Run scripts/batch_generate_audio.py")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
