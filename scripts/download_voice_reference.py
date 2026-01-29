#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Download voice reference from YouTube video for Qwen3-TTS voice cloning.

Usage:
    python scripts/download_voice_reference.py

Requirements:
    pip install yt-dlp pydub

The script will:
1. Download the audio from the YouTube video
2. Extract a clean segment of speech (10-30 seconds)
3. Save to voice_references/teacher_voice.wav
"""

import subprocess
import os
import sys
from pathlib import Path

# Configuration
VIDEO_URL = "https://www.youtube.com/watch?v=ym3HcmzNrf8"
OUTPUT_DIR = "voice_references"
OUTPUT_FILE = "teacher_voice_full.wav"
TRIMMED_FILE = "teacher_voice.wav"

# Time range for extraction (adjust based on video content)
# Format: start_time, duration in seconds
# Find a segment with clear speech, no background music
START_TIME = "00:00:10"  # Start at 10 seconds
DURATION = 20  # Extract 20 seconds


def main():
    # Change to project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    print("=" * 60)
    print("  VOICE REFERENCE DOWNLOADER")
    print("=" * 60)
    print(f"\n  Video URL: {VIDEO_URL}")
    print(f"  Output: {OUTPUT_DIR}/{TRIMMED_FILE}")
    print(f"  Duration: {DURATION} seconds")
    print("=" * 60 + "\n")

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    full_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    trimmed_path = os.path.join(OUTPUT_DIR, TRIMMED_FILE)

    # Step 1: Download full audio with yt-dlp
    print("[1/3] Downloading audio from YouTube...")
    try:
        # Remove existing file if any
        if os.path.exists(full_path):
            os.remove(full_path)

        result = subprocess.run([
            "yt-dlp",
            "-x",  # Extract audio only
            "--audio-format", "wav",
            "--audio-quality", "0",  # Best quality
            "-o", full_path,
            VIDEO_URL
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"  [ERROR] yt-dlp failed: {result.stderr}")
            # Try with different output format
            print("  [INFO] Trying alternative approach...")
            subprocess.run([
                "yt-dlp",
                "-x",  # Extract audio only
                "--audio-format", "wav",
                "-o", full_path.replace('.wav', '.%(ext)s'),
                VIDEO_URL
            ], check=True)

            # Find the downloaded file
            for ext in ['wav', 'webm', 'mp3', 'm4a']:
                test_path = full_path.replace('.wav', f'.{ext}')
                if os.path.exists(test_path):
                    full_path = test_path
                    break

        print(f"  [OK] Downloaded: {full_path}")

    except FileNotFoundError:
        print("  [ERROR] yt-dlp not found. Install with: pip install yt-dlp")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Download failed: {e}")
        sys.exit(1)

    # Step 2: Trim to specific segment using ffmpeg
    print(f"\n[2/3] Extracting {DURATION}s segment starting at {START_TIME}...")
    try:
        # Remove existing trimmed file if any
        if os.path.exists(trimmed_path):
            os.remove(trimmed_path)

        subprocess.run([
            "ffmpeg",
            "-i", full_path,
            "-ss", START_TIME,
            "-t", str(DURATION),
            "-acodec", "pcm_s16le",
            "-ar", "24000",  # 24kHz sample rate (good for TTS)
            "-ac", "1",  # Mono
            "-y",  # Overwrite
            trimmed_path
        ], check=True, capture_output=True)

        print(f"  [OK] Trimmed: {trimmed_path}")

    except FileNotFoundError:
        print("  [ERROR] ffmpeg not found. Please install ffmpeg.")
        print("  On Windows: choco install ffmpeg")
        print("  Or download from: https://ffmpeg.org/download.html")

        # Alternative: try using pydub
        print("\n  [INFO] Attempting fallback with pydub...")
        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_file(full_path)
            start_ms = 10 * 1000  # 10 seconds
            end_ms = start_ms + (DURATION * 1000)

            trimmed = audio[start_ms:end_ms]
            trimmed = trimmed.set_channels(1)  # Mono
            trimmed = trimmed.set_frame_rate(24000)  # 24kHz
            trimmed.export(trimmed_path, format="wav")

            print(f"  [OK] Trimmed with pydub: {trimmed_path}")

        except ImportError:
            print("  [ERROR] pydub not installed. Run: pip install pydub")
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Trimming failed: {e}")
        sys.exit(1)

    # Step 3: Create config file
    print("\n[3/3] Creating configuration file...")

    config_path = os.path.join(OUTPUT_DIR, "config.json")

    # Placeholder transcription - user must fill this in
    config_content = """{
  "ref_audio": "voice_references/teacher_voice.wav",
  "ref_text": "PLACEHOLDER: Transcribe the audio content here. Listen to the teacher_voice.wav file and type exactly what is said.",
  "language": "English",
  "speed": 0.85,
  "notes": "This transcription must match the audio exactly for best voice cloning results."
}
"""

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(config_content)

    print(f"  [OK] Config created: {config_path}")

    # Cleanup full file
    if os.path.exists(full_path) and full_path != trimmed_path:
        os.remove(full_path)
        print(f"  [OK] Cleaned up: {OUTPUT_FILE}")

    print("\n" + "=" * 60)
    print("  DOWNLOAD COMPLETE!")
    print("=" * 60)
    print(f"\n  Voice reference saved to: {trimmed_path}")
    print(f"  Duration: {DURATION} seconds")
    print("\n  IMPORTANT NEXT STEPS:")
    print("  1. Listen to the audio file and verify it has clear speech")
    print("  2. Edit voice_references/config.json")
    print("  3. Replace the placeholder text with the exact transcription")
    print("  4. The transcription must match what is said in the audio!")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
