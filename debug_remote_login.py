import requests
import json

BASE_URL = "https://ia-de-conversacao.vercel.app"

def test_remote():
    # 0. Test Debug Imports (GET)
    debug_url = f"{BASE_URL}/api/debug_imports"
    print(f"Testing GET {debug_url}...")
    try:
        r = requests.get(debug_url)
        print(f"Status: {r.status_code}")
        print(r.text[:500])
    except Exception as e:
        print(f"Debug check failed: {e}")

    print("-" * 20)

    # 1. Test Health (GET)
    health_url = f"{BASE_URL}/api/health"
    print(f"Testing GET {health_url}...")
    try:
        r = requests.get(health_url)
        print(f"Status: {r.status_code}")
        print(r.text[:200])
    except Exception as e:
        print(f"Health check failed: {e}")

    print("-" * 20)

    # 2. Test Login (POST)
    login_url = f"{BASE_URL}/api/auth/login"
    print(f"Testing POST {login_url}...")
    try:
        r = requests.post(login_url, json={"email": "everydayconversation1991@gmail.com", "password": "wrongpassword"})
        print(f"Status: {r.status_code}")
        print("Headers:", r.headers)
        if r.status_code == 405:
            print("Allow Header:", r.headers.get('Allow'))
        print("Body:", r.text[:200])
    except Exception as e:
        print(f"Login request failed: {e}")

if __name__ == "__main__":
    test_remote()
