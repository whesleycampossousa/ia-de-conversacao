import requests
import json

BASE_URL = "https://ia-de-conversacao.vercel.app"

def test_remote():
    # Check root URL content
    try:
        print(f"\nTesting GET {BASE_URL}/...")
        response = requests.get(f"{BASE_URL}/")
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
             # Print title to see what page it is
             import re
             title_match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
             if title_match:
                 print(f"Page Title: {title_match.group(1)}")
             else:
                 print("No title found.")
        else:
            print("Failed to fetch root.")
    except Exception as e:
        print(f"Error: {e}")

    print("-" * 20)

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
