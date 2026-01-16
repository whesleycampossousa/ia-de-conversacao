import requests
import os

BASE_URL = "https://ia-de-conversacao.vercel.app"
# BASE_URL = "http://localhost:4004" # Uncomment for local testing if needed

def run_tests():
    print(f"Target: {BASE_URL}")
    
    # 1. Login
    print("\n[1] AUTHENTICATION...")
    login_url = f"{BASE_URL}/api/auth/login"
    try:
        resp = requests.post(login_url, json={"email": "oliveiranfernandes@gmail.com"})
        if resp.status_code != 200:
            print(f"[FAIL] Login Failed: {resp.status_code} - {resp.text}")
            return
        
        token = resp.json().get('token')
        headers = {"Authorization": f"Bearer {token}"}
        print("[OK] Login Success")
    except Exception as e:
        print(f"[FAIL] Connection Error: {e}")
        return

    # 2. Test TTS (Generate Audio)
    print("\n[2] TESTING TTS (Google)...")
    tts_audio_path = "test_gen.mp3"
    try:
        resp = requests.post(
            f"{BASE_URL}/api/tts", 
            json={"text": "Hello, this is a test of the audio system.", "speed": 1.0},
            headers=headers
        )
        
        if resp.status_code == 200:
            with open(tts_audio_path, 'wb') as f:
                f.write(resp.content)
            print(f"[OK] TTS Success: Saved {len(resp.content)} bytes to {tts_audio_path}")
        else:
            print(f"[FAIL] TTS Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[FAIL] TTS Error: {e}")

    # 3. Test Transcription (Groq)
    print("\n[3] TESTING TRANSCRIPTION (Groq)...")
    if not os.path.exists(tts_audio_path):
        print("[FAIL] Skipping Transcription check (No audio file to upload)")
        return

    try:
        with open(tts_audio_path, 'rb') as f:
            files = {'audio': ('test.mp3', f, 'audio/mpeg')}
            # Note: /api/transcribe expects multipart/form-data
            # We must NOT set Content-Type header manually, requests does it with boundary
            trans_headers = {"Authorization": f"Bearer {token}"} 
            
            resp = requests.post(
                f"{BASE_URL}/api/transcribe",
                files=files,
                headers=trans_headers
            )
            
            if resp.status_code == 200:
                print(f"[OK] Transcription Success!")
                print(f"   Result: {resp.json()}")
            else:
                print(f"[FAIL] Transcription Failed: {resp.status_code} - {resp.text}")

    except Exception as e:
        print(f"[FAIL] Transcription Error: {e}")

if __name__ == "__main__":
    run_tests()
