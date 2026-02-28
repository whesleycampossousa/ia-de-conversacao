#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para testar as 3 vozes em português
"""
import os
import sys
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '').strip()

if not GOOGLE_API_KEY:
    print("ERRO: GOOGLE_API_KEY não configurada!")
    sys.exit(1)

# Vozes em português
VOZES = {
    'Sara': 'pt-BR-Neural2-C',
    'Emma': 'pt-BR-Neural2-A',
    'Tiago': 'pt-BR-Neural2-B'
}

TEXTO_TESTE = "Olá! Esta é uma voz de teste em português brasileiro."

url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_API_KEY}"

print("="*60)
print("TESTE DAS 3 VOZES EM PORTUGUÊS")
print("="*60)
print()

for nome, voz_id in VOZES.items():
    print(f"Testando voz: {nome} ({voz_id})...")
    
    payload = {
        "input": {"text": TEXTO_TESTE},
        "voice": {
            "languageCode": "pt-BR",
            "name": voz_id,
            "ssmlGender": "MALE" if nome == "Tiago" else "FEMALE"
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": 1.0
        }
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        
        if response.status_code == 200:
            audio_content = base64.b64decode(response.json()['audioContent'])
            filename = f"teste_{nome.lower()}.mp3"
            with open(filename, 'wb') as f:
                f.write(audio_content)
            print(f"  ✅ SUCESSO! Áudio salvo em: {filename}")
            print(f"  📊 Tamanho: {len(audio_content)} bytes")
        else:
            print(f"  ❌ ERRO {response.status_code}: {response.text[:200]}")
            
    except Exception as e:
        print(f"  ❌ ERRO: {e}")
    
    print()

print("="*60)
print("Teste concluído! Reproduza os arquivos para verificar as diferenças.")
print("="*60)
