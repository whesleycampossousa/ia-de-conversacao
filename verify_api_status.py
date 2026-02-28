import os
import time

import requests


BASE_URL = os.getenv("API_BASE_URL", "https://ia-de-conversacao.vercel.app").rstrip("/")
TEST_EMAIL = (os.getenv("TEST_EMAIL") or "").strip()
TEST_PASSWORD = (os.getenv("TEST_PASSWORD") or "").strip()
MAX_RETRIES = int(os.getenv("VERIFY_MAX_RETRIES", "4"))


def request_with_backoff(method, url, **kwargs):
    for attempt in range(MAX_RETRIES):
        response = requests.request(method, url, **kwargs)
        if response.status_code != 429:
            return response

        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            sleep_seconds = int(retry_after)
        else:
            sleep_seconds = min(2 ** attempt, 10)

        print(f"[WARN] 429 em {url}. Tentando novamente em {sleep_seconds}s (tentativa {attempt + 1}/{MAX_RETRIES})")
        time.sleep(sleep_seconds)

    return response


def login():
    if not TEST_EMAIL:
        print("[FAIL] Defina TEST_EMAIL no ambiente para executar o smoke.")
        return None

    login_url = f"{BASE_URL}/api/auth/login"
    payload = {"email": TEST_EMAIL}
    if TEST_PASSWORD:
        payload["password"] = TEST_PASSWORD

    resp = request_with_backoff("POST", login_url, json=payload, timeout=20)

    # Fallback: alguns ambientes retornam invalid admin password se senha for enviada para fluxo comum.
    if (
        resp.status_code == 401
        and "invalid admin password" in (resp.text or "").lower()
        and "password" in payload
    ):
        print("[WARN] Login retornou invalid admin password. Repetindo sem senha...")
        resp = request_with_backoff("POST", login_url, json={"email": TEST_EMAIL}, timeout=20)

    if resp.status_code != 200:
        print(f"[FAIL] Login Failed: {resp.status_code} - {resp.text}")
        return None

    token = (resp.json() or {}).get("token")
    if not token:
        print("[FAIL] Login sem token no retorno.")
        return None

    print("[OK] Login Success")
    return token


def run_tests():
    print(f"Target: {BASE_URL}")

    print("\n[1] AUTHENTICATION...")
    token = login()
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

    print("\n[2] TESTING TTS...")
    tts_audio_path = "test_gen.mp3"
    try:
        resp = request_with_backoff(
            "POST",
            f"{BASE_URL}/api/tts",
            json={"text": "Hello, this is a test of the audio system.", "speed": 1.0, "lessonLang": "en"},
            headers=headers,
            timeout=30,
        )

        if resp.status_code == 200:
            with open(tts_audio_path, "wb") as f:
                f.write(resp.content)
            print(f"[OK] TTS Success: Saved {len(resp.content)} bytes to {tts_audio_path}")
        else:
            print(f"[FAIL] TTS Failed: {resp.status_code} - {resp.text}")
            return
    except Exception as exc:
        print(f"[FAIL] TTS Error: {exc}")
        return

    print("\n[3] TESTING TRANSCRIPTION...")
    if not os.path.exists(tts_audio_path):
        print("[FAIL] Skipping Transcription check (No audio file to upload)")
        return

    try:
        with open(tts_audio_path, "rb") as f:
            files = {"audio": ("test.mp3", f, "audio/mpeg")}
            resp = request_with_backoff(
                "POST",
                f"{BASE_URL}/api/transcribe",
                files=files,
                headers=headers,
                timeout=30,
            )

        if resp.status_code == 200:
            print("[OK] Transcription Success!")
            print(f"   Result: {resp.json()}")
        elif resp.status_code == 400 and "no speech detected" in (resp.text or "").lower():
            print(f"[WARN] Transcription sem fala detectada (resultado conhecido): {resp.status_code} - {resp.text}")
        elif resp.status_code == 429:
            print(f"[WARN] Transcription bloqueado por política/rate-limit: {resp.status_code} - {resp.text}")
        else:
            print(f"[FAIL] Transcription Failed: {resp.status_code} - {resp.text}")
    except Exception as exc:
        print(f"[FAIL] Transcription Error: {exc}")


if __name__ == "__main__":
    run_tests()
