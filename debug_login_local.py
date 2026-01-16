
import sys
import os
import json
from flask import Flask

# Add api folder to path to import index
sys.path.append(os.path.join(os.getcwd(), 'api'))

from index import app

def test_login():
    print("Testing Admin Login...")
    with app.test_client() as client:
        try:
            response = client.post('/api/auth/login', 
                json={
                    'email': 'everydayconversation1991@gmail.com', 
                    'password': '1234567'
                }
            )
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.get_data(as_text=True)}")
        except Exception as e:
            print(f"CRASHED: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_login()
