"""
One-off script: enroll a new Qwen voice clone for Portuguese using a local MP3.
Does NOT touch the existing EN clone — creates a parallel clone with a different prefix.

Run:
    .venv/Scripts/python.exe scripts/enroll_qwen_clone_pt.py

On success prints the new voice ID. Append it to .env as QWEN_TTS_CLONE_VOICE_PT=<value>.
"""
import base64
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    # Load .env from the worktree directory (one level up from scripts/)
    ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(ROOT / ".env")
except ImportError:
    ROOT = Path(__file__).resolve().parent.parent

API_KEY = os.environ.get("QWEN_API_KEY", "").strip() or os.environ.get("DASHSCOPE_API_KEY", "").strip()
if not API_KEY:
    print("ERROR: QWEN_API_KEY / DASHSCOPE_API_KEY missing in .env")
    sys.exit(1)

ENROLLMENT_URL = os.environ.get(
    "QWEN_VOICE_ENROLLMENT_ENDPOINT",
    "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/customization",
).strip()

TARGET_MODEL = os.environ.get("QWEN_TTS_CLONE_MODEL", "qwen3-tts-vc-2026-01-22").strip()
PREFIX = "clonept"  # distinct from the EN clone prefix (clone16)
AUDIO_FILE = ROOT / "voice_references" / "minha_voz_pt.mp3"

if not AUDIO_FILE.exists():
    print(f"ERROR: Audio file not found: {AUDIO_FILE}")
    sys.exit(1)

size = AUDIO_FILE.stat().st_size
if size > 2_000_000:
    print(f"ERROR: Audio file is {size} bytes — DashScope limit is 2MB")
    sys.exit(1)

print(f"Audio file: {AUDIO_FILE} ({size/1024:.1f} KB)")

with open(AUDIO_FILE, "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode("ascii")

mime = "audio/mpeg"  # mp3
data_uri = f"data:{mime};base64,{audio_b64}"

payload = {
    "model": "qwen-voice-enrollment",
    "input": {
        "action": "create",
        "target_model": TARGET_MODEL,
        "preferred_name": PREFIX,
        "audio": {
            "data": data_uri
        },
    },
}

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

print(f"Target model: {TARGET_MODEL}")
print(f"Preferred name: {PREFIX}")
print(f"Endpoint: {ENROLLMENT_URL}")
print("Submitting enrollment...")

try:
    resp = requests.post(ENROLLMENT_URL, headers=headers, json=payload, timeout=120)
except Exception as e:
    print(f"ERROR: Request failed: {e}")
    sys.exit(1)

print(f"HTTP {resp.status_code}")
try:
    data = resp.json()
except Exception:
    data = None

if resp.status_code != 200:
    print("Response body (first 800 chars):")
    print(resp.text[:800])
    sys.exit(1)

if not isinstance(data, dict):
    print("ERROR: Response was not JSON dict")
    print(resp.text[:800])
    sys.exit(1)

output = data.get("output") if isinstance(data.get("output"), dict) else {}
voice_id = str(output.get("voice") or "").strip()

if not voice_id:
    print("ERROR: Response didn't contain output.voice")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:800])
    sys.exit(1)

print("")
print("=" * 50)
print("SUCCESS")
print("=" * 50)
print(f"Voice ID: {voice_id}")
print("")
print("Add this to .env and Vercel:")
print(f"  QWEN_TTS_CLONE_VOICE_PT={voice_id}")
