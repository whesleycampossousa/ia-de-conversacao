"""
Script de teste para verificar se o TTS está funcionando
"""
import os
import sys
from dotenv import load_dotenv
from google.cloud import texttospeech

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

print("=" * 60)
print("TESTE DO TEXT-TO-SPEECH")
print("=" * 60)

if not GOOGLE_API_KEY:
    print("[X] ERRO: GOOGLE_API_KEY nao encontrada no .env")
    exit(1)

print(f"[OK] API Key encontrada: {GOOGLE_API_KEY[:10]}...")

try:
    print("\n1. Inicializando cliente TTS...")
    client = texttospeech.TextToSpeechClient(
        client_options={"api_key": GOOGLE_API_KEY}
    )
    print("[OK] Cliente inicializado com sucesso")

    print("\n2. Testando sintese de voz...")
    synthesis_input = texttospeech.SynthesisInput(text="Hello, this is a test.")

    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Neural2-C",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    print(f"[OK] Audio gerado com sucesso!")
    print(f"[OK] Tamanho do audio: {len(response.audio_content)} bytes")

    # Salvar arquivo de teste
    with open("test_audio.mp3", "wb") as out:
        out.write(response.audio_content)

    print("\n" + "=" * 60)
    print("[SUCESSO] TTS esta funcionando corretamente!")
    print("[SUCESSO] Arquivo de teste salvo: test_audio.mp3")
    print("=" * 60)

except Exception as e:
    print(f"\n[X] ERRO ao testar TTS:")
    print(f"   Tipo: {type(e).__name__}")
    print(f"   Mensagem: {str(e)}")

    if "403" in str(e):
        print("\n[!] SOLUCAO:")
        print("   1. Acesse: https://console.cloud.google.com/apis/library/texttospeech.googleapis.com")
        print("   2. Clique em 'ATIVAR' (ENABLE)")
        print("   3. Aguarde 1-2 minutos")
        print("   4. Execute este teste novamente")

    elif "401" in str(e):
        print("\n[!] SOLUCAO:")
        print("   A API Key pode estar invalida ou sem permissoes")
        print("   1. Verifique se a API Key esta correta no arquivo .env")
        print("   2. Acesse: https://console.cloud.google.com/apis/credentials")
        print("   3. Verifique as restricoes da API Key")

    import traceback
    print("\nDetalhes do erro:")
    print(traceback.format_exc())
