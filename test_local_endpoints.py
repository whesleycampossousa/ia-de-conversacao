import requests
import time
import sys

BASE_URL = "http://localhost:8912"

def test_endpoint(path, name):
    print(f"Testing {name} ({path})...", end=" ")
    try:
        resp = requests.get(f"{BASE_URL}{path}", timeout=2)
        if resp.status_code == 200:
            print(f"OK (Status 200)")
            try:
                data = resp.json()
                if isinstance(data, list):
                    print(f"  -> Got {len(data)} items")
                elif 'error' in data:
                     print(f"  -> Returned Error: {data['error']}")
                else:
                    print(f"  -> Got object with keys: {list(data.keys())}")
                return True
            except:
                print("  -> Failed to parse JSON")
                return False
        else:
            print(f"FAIL (Status {resp.status_code})")
            return False
    except requests.exceptions.ConnectionError:
        print("FAIL (Connection Refused - Server likely down)")
        return False
    except Exception as e:
        print(f"FAIL ({e})")
        return False

def run():
    print("Checking Local Server Connectivity...")
    
    # 1. Health
    server_up = test_endpoint("/api/health", "Health Check")
    if not server_up:
        # Backward-compatible alias check
        server_up = test_endpoint("/health", "Health Check Alias")
    
    if not server_up:
        print("\nServer appears strictly DOWN. Please start 'python api/index.py'")
        sys.exit(1)

    print("\nVerifying New Features...")
    # 2. Scenarios
    test_endpoint("/api/scenarios", "Scenarios DB")
    
    # 3. Grammar Topics
    test_endpoint("/api/grammar-topics", "Grammar Topics")

    print("\nDone.")

if __name__ == "__main__":
    run()
