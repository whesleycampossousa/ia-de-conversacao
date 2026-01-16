import requests
import json

URL = "https://ia-de-conversacao.vercel.app/api/auth/login"
EMAIL = "everydayconversation1991@gmail.com"
PASSWORD = "admin" # Guessing password or trying without match to see if we get past the initial crash

# Note: Admin password might be different, but we just want to see if it Crashes (500)
# or returns 401 (Invalid password), which would mean the server IS working.

def test_remote_login():
    print(f"Testing URL: {URL}")
    payload = {
        "email": EMAIL,
        "password": PASSWORD
    }
    
    try:
        response = requests.post(URL, json=payload, headers={"Content-Type": "application/json"})
        print(f"Status Code: {response.status_code}")
        try:
            print("Response JSON:")
            print(json.dumps(response.json(), indent=2))
        except:
            print("Response Text (Not JSON):")
            print(response.text)
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_remote_login()
