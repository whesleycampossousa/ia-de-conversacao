"""
Teste rápido do chat
"""
import os
import sys
from dotenv import load_dotenv
import google.generativeai as genai

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

print("Testando API de Chat...")
print(f"API Key: {GOOGLE_API_KEY[:10]}...")

try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-pro')

    print("\nEnviando mensagem de teste...")
    response = model.generate_content("Hello, how are you?")

    print(f"\nResposta: {response.text}")
    print("\n[OK] Chat funcionando!")

except Exception as e:
    print(f"\n[ERRO] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
