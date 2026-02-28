
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

with open("models.txt", "w") as f:
    for m in genai.list_models():
        f.write(f"{m.name}\n")
print("Models listed to models.txt")
