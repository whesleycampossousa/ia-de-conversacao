#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Batch generate audio files for all lesson phrases using voice cloning.

Usage:
    python scripts/batch_generate_audio.py [--resume] [--limit N]

Requirements:
    1. Run extract_lesson_phrases.py first to create phrases_to_generate.json
    2. Run download_voice_reference.py and transcribe the audio
    3. Make sure the API server is running (python start_server.py)
    4. Make sure Qwen3-TTS server is running with QWEN_TTS_URL configured

Options:
    --resume    Resume from last successful generation
    --limit N   Only generate N phrases (for testing)
    --dry-run   Don't actually generate, just show what would be done
"""

import json
import requests
import os
import sys
import time
import hashlib
import argparse
from pathlib import Path
from datetime import datetime


# Configuration
OUTPUT_DIR = "audio_cache/lessons"
PHRASES_FILE = "scripts/phrases_to_generate.json"
PROGRESS_FILE = "scripts/generation_progress.json"
API_URL = "http://localhost:8912/api/tts/clone"
SPEED = 0.85
TIMEOUT = 60  # seconds
RETRY_COUNT = 3
DELAY_BETWEEN_REQUESTS = 0.5  # seconds


def get_cache_filename(phrase_id: str, text: str) -> str:
    """Generate unique filename for cached audio."""
    # Use hash of text for uniqueness
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    # Sanitize phrase_id for filename
    safe_id = phrase_id.replace('/', '_').replace('\\', '_')
    return f"{safe_id}_{text_hash}.mp3"


def load_progress(progress_file: str) -> dict:
    """Load generation progress from file."""
    if os.path.exists(progress_file):
        with open(progress_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"completed": [], "failed": [], "last_index": 0}


def save_progress(progress_file: str, progress: dict):
    """Save generation progress to file."""
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2)


def generate_audio(text: str, speed: float = 0.85) -> bytes:
    """Generate audio using the TTS clone API."""
    response = requests.post(
        API_URL,
        json={
            "text": text,
            "speed": speed
        },
        timeout=TIMEOUT
    )

    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"API error: {response.status_code} - {response.text[:200]}")


def main():
    parser = argparse.ArgumentParser(description='Batch generate TTS audio for lessons')
    parser.add_argument('--resume', action='store_true', help='Resume from last progress')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of phrases to generate')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without generating')
    args = parser.parse_args()

    # Change to project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    print("=" * 60)
    print("  BATCH AUDIO GENERATOR (Voice Cloning)")
    print("=" * 60)
    print(f"\n  Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Speed: {SPEED}x")
    print(f"  Output: {OUTPUT_DIR}/")
    print("=" * 60 + "\n")

    # Check if phrases file exists
    if not os.path.exists(PHRASES_FILE):
        print(f"[ERROR] Phrases file not found: {PHRASES_FILE}")
        print("Run extract_lesson_phrases.py first!")
        sys.exit(1)

    # Load phrases
    print("[1/4] Loading phrases...")
    with open(PHRASES_FILE, 'r', encoding='utf-8') as f:
        phrases = json.load(f)
    print(f"  Loaded {len(phrases)} phrases")

    # Apply limit if specified
    if args.limit > 0:
        phrases = phrases[:args.limit]
        print(f"  Limited to {len(phrases)} phrases (--limit {args.limit})")

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load or initialize progress
    print("\n[2/4] Checking progress...")
    progress = load_progress(PROGRESS_FILE) if args.resume else {"completed": [], "failed": [], "last_index": 0}

    if args.resume and progress['completed']:
        print(f"  Resuming: {len(progress['completed'])} already completed")
    else:
        print("  Starting fresh")

    # Check API availability
    print("\n[3/4] Testing API connection...")
    if not args.dry_run:
        try:
            test_response = requests.get("http://localhost:8912/api/health", timeout=5)
            if test_response.status_code == 200:
                print("  [OK] API server is running")
            else:
                print(f"  [WARNING] API returned status {test_response.status_code}")
        except requests.exceptions.ConnectionError:
            print("  [ERROR] Cannot connect to API server at http://localhost:8912")
            print("  Make sure the server is running: python start_server.py")
            sys.exit(1)
        except Exception as e:
            print(f"  [WARNING] API check failed: {e}")

    # Generate audio
    print("\n[4/4] Generating audio files...")
    print("-" * 60)

    total = len(phrases)
    success_count = len(progress['completed'])
    failed_count = 0
    skipped_count = 0

    for i, phrase in enumerate(phrases):
        phrase_id = phrase['id']
        text = phrase['text']
        filename = get_cache_filename(phrase_id, text)
        filepath = os.path.join(OUTPUT_DIR, filename)

        # Skip if already completed
        if phrase_id in progress['completed']:
            skipped_count += 1
            continue

        # Skip if file already exists
        if os.path.exists(filepath):
            progress['completed'].append(phrase_id)
            success_count += 1
            skipped_count += 1
            print(f"[{i+1}/{total}] SKIP (exists): {phrase_id}")
            continue

        if args.dry_run:
            print(f"[{i+1}/{total}] WOULD GENERATE: {phrase_id}")
            print(f"         Text: {text[:50]}...")
            print(f"         File: {filename}")
            continue

        # Generate audio with retries
        for attempt in range(RETRY_COUNT):
            try:
                audio_data = generate_audio(text, SPEED)

                # Verify audio data
                if len(audio_data) < 100:
                    raise Exception(f"Audio data too small: {len(audio_data)} bytes")

                # Save to file
                with open(filepath, 'wb') as f:
                    f.write(audio_data)

                progress['completed'].append(phrase_id)
                success_count += 1
                print(f"[{i+1}/{total}] OK: {phrase_id} ({len(audio_data)} bytes)")
                break

            except Exception as e:
                if attempt < RETRY_COUNT - 1:
                    print(f"[{i+1}/{total}] RETRY ({attempt+1}/{RETRY_COUNT}): {phrase_id} - {e}")
                    time.sleep(1)
                else:
                    print(f"[{i+1}/{total}] FAIL: {phrase_id} - {e}")
                    progress['failed'].append({"id": phrase_id, "error": str(e)})
                    failed_count += 1

        # Save progress periodically
        if (i + 1) % 50 == 0:
            progress['last_index'] = i
            save_progress(PROGRESS_FILE, progress)
            print(f"         Progress saved ({success_count}/{total})")

        # Rate limiting
        time.sleep(DELAY_BETWEEN_REQUESTS)

    # Final progress save
    progress['last_index'] = total
    save_progress(PROGRESS_FILE, progress)

    # Summary
    print("\n" + "=" * 60)
    print("  GENERATION COMPLETE!")
    print("=" * 60)
    print(f"\n  End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n  Results:")
    print(f"    Total phrases:     {total}")
    print(f"    Successfully generated: {success_count}")
    print(f"    Skipped (existed): {skipped_count}")
    print(f"    Failed:            {failed_count}")

    if failed_count > 0:
        print(f"\n  Failed phrases saved to: {PROGRESS_FILE}")
        print("  Re-run with --resume to retry failed items")

    # List generated files
    generated_files = os.listdir(OUTPUT_DIR)
    print(f"\n  Files in {OUTPUT_DIR}/: {len(generated_files)}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
