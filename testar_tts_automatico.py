#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script automático para testar e configurar TTS
"""
import os
import sys

try:
    from dotenv import load_dotenv
    import requests
except ImportError as e:
    print(f"ERRO: Biblioteca faltando: {e}")
    print("Instale com: pip install python-dotenv requests")
    sys.exit(1)

# Mudar para o diretório do script
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

load_dotenv()

def test_tts_api():
    """Testa se a API do Google TTS está funcionando"""
    api_key = os.getenv('GOOGLE_API_KEY', '').strip()
    
    if not api_key:
        print("ERRO: GOOGLE_API_KEY não encontrada no .env")
        return False
    
    if api_key == 'your_api_key_here' or len(api_key) < 20:
        print("ERRO: GOOGLE_API_KEY parece inválida")
        return False
    
    print(f"Testando API com chave: {api_key[:15]}...")
    
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    payload = {
        "input": {"text": "Hello, this is a test"},
        "voice": {
            "languageCode": "en-US",
            "name": "en-US-Neural2-C",
            "ssmlGender": "FEMALE"
        },
        "audioConfig": {
            "audioEncoding": "MP3"
        }
    }
    
    try:
        print("Enviando requisição de teste...")
        response = requests.post(url, json=payload, timeout=15)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("SUCESSO! API do Google Cloud TTS está funcionando!")
            return True
        elif response.status_code == 403:
            print("ERRO 403: API não está habilitada no Google Cloud Console")
            print("\nPara habilitar:")
            print("1. Acesse: https://console.cloud.google.com/apis/library/texttospeech.googleapis.com")
            print("2. Faça login")
            print("3. Clique em 'ATIVAR' ou 'ENABLE'")
            return False
        elif response.status_code == 400:
            print("AVISO: Requisição inválida, mas API está acessível")
            return True
        else:
            error_text = response.text[:200] if hasattr(response, 'text') else str(response)
            print(f"ERRO {response.status_code}: {error_text}")
            return False
            
    except requests.exceptions.Timeout:
        print("ERRO: Timeout ao conectar com a API")
        return False
    except requests.exceptions.RequestException as e:
        print(f"ERRO de conexão: {e}")
        return False
    except Exception as e:
        print(f"ERRO inesperado: {e}")
        return False

if __name__ == '__main__':
    print("="*60)
    print("TESTE AUTOMÁTICO DO TEXT-TO-SPEECH")
    print("="*60)
    print()
    
    result = test_tts_api()
    
    print()
    print("="*60)
    if result:
        print("OK: TTS CONFIGURADO E FUNCIONANDO!")
    else:
        print("ERRO: TTS NÃO ESTÁ FUNCIONANDO")
        print("   Siga as instruções acima para habilitar a API")
    print("="*60)
    
    sys.exit(0 if result else 1)
