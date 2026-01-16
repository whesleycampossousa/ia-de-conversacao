"""Lista modelos disponíveis do Gemini"""
import os
import sys
from dotenv import load_dotenv
import google.generativeai as genai

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

try:
    genai.configure(api_key=GOOGLE_API_KEY)

    print("Modelos disponiveis:")
    print("=" * 60)

    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
            print(f"  Display: {m.display_name}")
            print(f"  Desc: {m.description[:100] if m.description else 'N/A'}...")
            print()

except Exception as e:
    print(f"Erro: {e}")
    import traceback
    traceback.print_exc()
