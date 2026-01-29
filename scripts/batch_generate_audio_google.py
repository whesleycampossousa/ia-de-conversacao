#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Batch generate audio files for all lesson phrases using Google TTS.

This is a fallback script when Qwen3-TTS voice cloning is not available.
It uses the regular /api/tts endpoint with Google Cloud TTS.

Usage:
    python scripts/batch_generate_audio_google.py [--resume] [--limit N]

Requirements:
    1. Run extract_lesson_phrases.py first
    2. Make sure the API server is running (python start_server.py)
    3. Google Cloud TTS API key must be configured
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
PROGRESS_FILE = "scripts/generation_progress_google.json"
API_URL = "http://localhost:8912/api/tts"
SPEED = 0.85
TIMEOUT = 30
RETRY_COUNT = 3
DELAY_BETWEEN_REQUESTS = 0.3


def get_cache_filename(phrase_id: str, text: str) -> str:
    """Generate unique filename for cached audio."""
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
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


def get_auth_token():
    """Get authentication token from the API."""
    try:
        # Try to login or use a test token
        response = requests.post(
            "http://localhost:8912/api/auth/login",
            json={"email": "test@test.com", "password": "test123"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get('token')
    except:
        pass
    return None


def generate_audio(text: str, speed: float, token: str = None) -> bytes:
    """Generate audio using the TTS API."""
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    response = requests.post(
        API_URL,
        json={
            "text": text,
            "speed": speed,
            "lessonLang": "en",
            "voice": "female1"
        },
        headers=headers,
        timeout=TIMEOUT
    )

    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"API error: {response.status_code} - {response.text[:200]}")


def main():
    parser = argparse.ArgumentParser(description='Batch generate TTS audio using Google TTS')
    parser.add_argument('--resume', action='store_true', help='Resume from last progress')
    parser.add_argument('--limit', type=int, default=0, help='Limit number of phrases')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    print("=" * 60)
    print("  BATCH AUDIO GENERATOR (Google TTS)")
    print("=" * 60)
    print(f"\n  Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Speed: {SPEED}x")
    print(f"  Output: {OUTPUT_DIR}/")
    print("=" * 60 + "\n")

    if not os.path.exists(PHRASES_FILE):
        print(f"[ERROR] Phrases file not found: {PHRASES_FILE}")
        print("Run extract_lesson_phrases.py first!")
        sys.exit(1)

    print("[1/4] Loading phrases...")
    with open(PHRASES_FILE, 'r', encoding='utf-8') as f:
        phrases = json.load(f)
    print(f"  Loaded {len(phrases)} phrases")

    if args.limit > 0:
        phrases = phrases[:args.limit]
        print(f"  Limited to {len(phrases)} phrases")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("\n[2/4] Checking progress...")
    progress = load_progress(PROGRESS_FILE) if args.resume else {"completed": [], "failed": [], "last_index": 0}

    if args.resume and progress['completed']:
        print(f"  Resuming: {len(progress['completed'])} already completed")

    print("\n[3/4] Testing API connection...")
    if not args.dry_run:
        try:
            response = requests.get("http://localhost:8912/api/health", timeout=5)
            if response.status_code == 200:
                print("  [OK] API server is running")
            else:
                print(f"  [WARNING] API returned status {response.status_code}")
        except requests.exceptions.ConnectionError:
            print("  [ERROR] Cannot connect to API server")
            print("  Start the server: python start_server.py")
            sys.exit(1)

    # Get auth token
    token = get_auth_token()
    if token:
        print("  [OK] Authentication successful")
    else:
        print("  [WARNING] No authentication - some requests may fail")

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

        if phrase_id in progress['completed']:
            skipped_count += 1
            continue

        if os.path.exists(filepath):
            progress['completed'].append(phrase_id)
            success_count += 1
            skipped_count += 1
            continue

        if args.dry_run:
            print(f"[{i+1}/{total}] WOULD GENERATE: {phrase_id}")
            continue

        for attempt in range(RETRY_COUNT):
            try:
                audio_data = generate_audio(text, SPEED, token)

                if len(audio_data) < 100:
                    raise Exception(f"Audio too small: {len(audio_data)} bytes")

                with open(filepath, 'wb') as f:
                    f.write(audio_data)

                progress['completed'].append(phrase_id)
                success_count += 1
                print(f"[{i+1}/{total}] OK: {phrase_id} ({len(audio_data)} bytes)")
                break

            except Exception as e:
                if attempt < RETRY_COUNT - 1:
                    print(f"[{i+1}/{total}] RETRY: {phrase_id} - {e}")
                    time.sleep(1)
                else:
                    print(f"[{i+1}/{total}] FAIL: {phrase_id} - {e}")
                    progress['failed'].append({"id": phrase_id, "error": str(e)})
                    failed_count += 1

        if (i + 1) % 50 == 0:
            progress['last_index'] = i
            save_progress(PROGRESS_FILE, progress)

        time.sleep(DELAY_BETWEEN_REQUESTS)

    save_progress(PROGRESS_FILE, progress)

    print("\n" + "=" * 60)
    print("  GENERATION COMPLETE!")
    print("=" * 60)
    print(f"\n  Results:")
    print(f"    Total: {total}")
    print(f"    Success: {success_count}")
    print(f"    Skipped: {skipped_count}")
    print(f"    Failed: {failed_count}")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
