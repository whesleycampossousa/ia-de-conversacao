
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY not found.")
    exit(1)


genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-exp')

safety_settings = [
    { "category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE" },
    { "category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE" },
    { "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE" },
    { "category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE" }
]


print("Testing safety settings syntax...")
with open("error_log.txt", "w") as f:
    try:
        response = model.generate_content("Hello, how are you?", safety_settings=safety_settings)
        print("Success! Response:", response.text)
        f.write("Success with safe prompt\n")
    except Exception as e:
        print("Error with safe prompt:", e)
        f.write(f"Error with safe prompt: {e}\n")

    print("\nTesting borderline prompt...")
    try:
        # A prompt that might trigger mild safety filters without being truly harmful
        response = model.generate_content("I hate everything about this stupid situation.", safety_settings=safety_settings)
        print("Success! Response:", response.text)
        f.write("Success with borderline prompt\n")
    except Exception as e:
        print("Error with borderline prompt:", e)
        f.write(f"Error with borderline prompt: {e}\n")

