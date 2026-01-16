"""Lista todas as vozes disponíveis do Google Cloud TTS"""
import os
import sys
from dotenv import load_dotenv
from google.cloud import texttospeech

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

try:
    client = texttospeech.TextToSpeechClient(
        client_options={"api_key": GOOGLE_API_KEY}
    )

    # Lista todas as vozes
    voices = client.list_voices()

    print("=" * 80)
    print("VOZES FEMININAS EM INGLES (NEURAL2 E STUDIO)")
    print("=" * 80)

    # Filtrar apenas vozes femininas em inglês americano
    female_voices = []
    for voice in voices.voices:
        if voice.language_codes[0].startswith('en-US'):
            if voice.ssml_gender == texttospeech.SsmlVoiceGender.FEMALE:
                female_voices.append(voice)

    # Ordenar: Studio primeiro, depois Neural2, depois outras
    female_voices.sort(key=lambda v: (
        0 if 'Studio' in v.name else 1 if 'Neural2' in v.name else 2,
        v.name
    ))

    for voice in female_voices:
        quality = ""
        if 'Studio' in voice.name:
            quality = "[MELHOR QUALIDADE - Studio]"
        elif 'Neural2' in voice.name:
            quality = "[Alta Qualidade - Neural2]"
        elif 'Wavenet' in voice.name:
            quality = "[Boa Qualidade - WaveNet]"
        else:
            quality = "[Standard]"

        print(f"\n{voice.name} {quality}")
        print(f"  Idioma: {', '.join(voice.language_codes)}")
        print(f"  Taxa: {voice.natural_sample_rate_hertz} Hz")

    print("\n" + "=" * 80)
    print("RECOMENDACOES:")
    print("=" * 80)
    print("1. en-US-Studio-O ou en-US-Studio-M (MELHOR - mais natural e expressiva)")
    print("2. en-US-Neural2-C, E, F, G, H (ALTA - muito boa)")
    print("3. en-US-Wavenet-* (BOA - qualidade acima da media)")
    print("\nATUAL: en-US-Neural2-C")

except Exception as e:
    print(f"Erro: {e}")
    import traceback
    traceback.print_exc()
