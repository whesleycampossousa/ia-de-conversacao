import os
import sys
from dotenv import load_dotenv

# Load env vars
load_dotenv()

def check_keys():
    print("Verificando chaves de API...")
    
    # 1. Check Groq
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key and groq_key.startswith("gsk_"):
        print("[OK] GROQ_API_KEY: Configurada")
    else:
        print("[ERROR] GROQ_API_KEY: Faltando ou invalida")
        
    # 2. Check Google
    google_key = os.getenv("GOOGLE_API_KEY")
    if google_key and google_key.startswith("AIza"):
        print("[OK] GOOGLE_API_KEY: Configurada")
    else:
        print("[ERROR] GOOGLE_API_KEY: Faltando ou invalida")
        
    if groq_key and google_key:
        print("\n[SUCCESS] CONFIGURACAO OK - Audio deve funcionar!")
    else:
        print("\n[WARNING] Algumas configuracoes de audio estao faltando.")

if __name__ == "__main__":
    check_keys()
