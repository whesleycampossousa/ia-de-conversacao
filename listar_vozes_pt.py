#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para listar todas as vozes disponíveis em português brasileiro
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '').strip()

if not GOOGLE_API_KEY:
    print("ERRO: GOOGLE_API_KEY não configurada!")
    exit(1)

url = f"https://texttospeech.googleapis.com/v1/voices?key={GOOGLE_API_KEY}"

try:
    response = requests.get(url, timeout=15)
    
    if response.status_code != 200:
        print(f"ERRO {response.status_code}: {response.text}")
        exit(1)
    
    data = response.json()
    voices = data.get('voices', [])
    
    # Filtrar apenas vozes em português brasileiro
    pt_voices = [v for v in voices if 'pt-BR' in v.get('languageCodes', [])]
    
    print("="*80)
    print("VOZES DISPONÍVEIS EM PORTUGUÊS BRASILEIRO (pt-BR)")
    print("="*80)
    print()
    
    # Agrupar por tipo
    by_type = {}
    for voice in pt_voices:
        voice_type = voice.get('ssmlVoiceGender', 'UNKNOWN')
        name = voice.get('name', '')
        
        if 'Studio' in name:
            vtype = 'Studio (10x mais caro)'
        elif 'Neural2' in name:
            vtype = 'Neural2 (Atual)'
        elif 'Wavenet' in name:
            vtype = 'Wavenet'
        elif 'Standard' in name:
            vtype = 'Standard'
        else:
            vtype = 'Outro'
        
        if vtype not in by_type:
            by_type[vtype] = []
        by_type[vtype].append(voice)
    
    # Mostrar Neural2 primeiro (que estamos usando)
    for vtype in ['Neural2 (Atual)', 'Studio (10x mais caro)', 'Wavenet', 'Standard', 'Outro']:
        if vtype not in by_type:
            continue
        
        print(f"\n{'='*80}")
        print(f"  {vtype.upper()}")
        print(f"{'='*80}")
        
        for voice in sorted(by_type[vtype], key=lambda x: x.get('name', '')):
            name = voice.get('name', '')
            gender = voice.get('ssmlVoiceGender', 'UNKNOWN')
            natural_sample_rate = voice.get('naturalSampleRateHertz', 0)
            
            print(f"\n  Nome: {name}")
            print(f"  Gênero: {gender}")
            print(f"  Taxa de amostragem: {natural_sample_rate} Hz")
            
            # Verificar se é melhor que Neural2
            if 'Studio' in name:
                print(f"  ⚠️  PREÇO: 10x mais caro que Neural2 ($160 vs $16 por 1M caracteres)")
                print(f"  ✅ QUALIDADE: Muito mais realista, ideal para narração profissional")
            elif 'Neural2' in name:
                print(f"  💰 PREÇO: $16 por 1 milhão de caracteres")
                print(f"  ✅ QUALIDADE: Boa qualidade, natural e expressiva")
    
    print("\n" + "="*80)
    print("RECOMENDAÇÃO:")
    print("="*80)
    print("Neural2 já oferece excelente qualidade a um preço acessível.")
    print("Studio voices são 10x mais caras e são para uso profissional/narração.")
    print("Para ensino de idiomas, Neural2 é a melhor opção custo-benefício.")
    print("="*80)
    
except Exception as e:
    print(f"ERRO: {e}")
    import traceback
    traceback.print_exc()
