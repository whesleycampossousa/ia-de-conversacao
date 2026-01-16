import requests

# Test TTS endpoint
url = "https://ia-de-conversacao.vercel.app/api/tts"
payload = {"text": "Hello, how are you?", "speed": 1.0}

# Need auth token - get one first
login_url = "https://ia-de-conversacao.vercel.app/api/auth/login"
login_response = requests.post(login_url, json={"email": "oliveiranfernandes@gmail.com"})
print(f"Login Status: {login_response.status_code}")
print(f"Login Response: {login_response.text[:200]}")

if login_response.status_code == 200:
    token = login_response.json().get('token')
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    tts_response = requests.post(url, json=payload, headers=headers)
    print(f"\nTTS Status: {tts_response.status_code}")
    print(f"TTS Headers: {dict(tts_response.headers)}")
    
    if tts_response.status_code == 200:
        print(f"TTS Content Length: {len(tts_response.content)} bytes")
        with open("test_output.mp3", "wb") as f:
            f.write(tts_response.content)
        print("Audio saved to test_output.mp3")
    else:
        print(f"TTS Error: {tts_response.text[:500]}")
