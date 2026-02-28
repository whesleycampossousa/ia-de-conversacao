#!/usr/bin/env python3
"""
Script para configurar e verificar o Text-to-Speech
"""
import os
import sys
from pathlib import Path

# Cores para terminal
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}[OK] {text}{Colors.RESET}")

def print_error(text):
    print(f"{Colors.RED}[ERRO] {text}{Colors.RESET}")

def print_warning(text):
    print(f"{Colors.YELLOW}[AVISO] {text}{Colors.RESET}")

def print_info(text):
    print(f"{Colors.BLUE}[INFO] {text}{Colors.RESET}")

def check_env_file():
    """Verifica se o arquivo .env existe"""
    env_path = Path('.env')
    if not env_path.exists():
        print_error("Arquivo .env não encontrado!")
        print_info("Criando arquivo .env a partir do .env.example...")
        
        example_path = Path('.env.example')
        if example_path.exists():
            with open(example_path, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print_success("Arquivo .env criado!")
        else:
            print_error("Arquivo .env.example não encontrado!")
            return False
    return True

def load_env():
    """Carrega variáveis do .env"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return True
    except ImportError:
        print_error("python-dotenv não instalado!")
        print_info("Instale com: pip install python-dotenv")
        return False

def check_google_api_key():
    """Verifica se a GOOGLE_API_KEY está configurada"""
    key = os.getenv('GOOGLE_API_KEY', '').strip()
    
    if not key:
        print_error("GOOGLE_API_KEY não configurada!")
        print_info("Obtenha sua chave em: https://aistudio.google.com/app/apikey")
        return False
    
    if key == 'your_api_key_here' or len(key) < 20:
        print_error("GOOGLE_API_KEY parece inválida!")
        print_info("Verifique se você colou a chave completa no arquivo .env")
        return False
    
    print_success(f"GOOGLE_API_KEY configurada (primeiros caracteres: {key[:15]}...)")
    return True

def check_groq_api_key():
    """Verifica se a GROQ_API_KEY está configurada"""
    key = os.getenv('GROQ_API_KEY', '').strip()
    
    if not key:
        print_warning("GROQ_API_KEY não configurada (opcional para transcrição)")
        print_info("Obtenha em: https://console.groq.com/keys")
        return False
    
    print_success(f"GROQ_API_KEY configurada (primeiros caracteres: {key[:15]}...)")
    return True

def test_tts_api():
    """Testa se a API do Google TTS está acessível"""
    import requests
    
    api_key = os.getenv('GOOGLE_API_KEY', '').strip()
    if not api_key:
        return False
    
    print_info("Testando conexão com Google Cloud TTS API...")
    
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    payload = {
        "input": {"text": "Test"},
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
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            print_success("Google Cloud TTS API está funcionando!")
            return True
        elif response.status_code == 403:
            print_error("API do Google Cloud Text-to-Speech NÃO está habilitada!")
            print_info("Habilite em: https://console.cloud.google.com/apis/library/texttospeech.googleapis.com")
            print_info("1. Acesse o link acima")
            print_info("2. Faça login com a mesma conta do Gemini")
            print_info("3. Clique em 'ATIVAR' ou 'ENABLE'")
            print_info("4. Aguarde 1-2 minutos")
            return False
        elif response.status_code == 400:
            print_warning("Requisição inválida, mas a API está acessível")
            return True
        else:
            print_error(f"Erro ao testar API: Status {response.status_code}")
            print_info(f"Resposta: {response.text[:200]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print_error(f"Erro de conexão: {e}")
        return False

def main():
    print_header("CONFIGURAÇÃO DO TEXT-TO-SPEECH")
    
    # 1. Verificar arquivo .env
    if not check_env_file():
        return 1
    
    # 2. Carregar variáveis
    if not load_env():
        return 1
    
    # 3. Verificar chaves
    google_ok = check_google_api_key()
    groq_ok = check_groq_api_key()
    
    if not google_ok:
        print("\n" + "="*60)
        print_error("CONFIGURAÇÃO INCOMPLETA")
        print_info("1. Abra o arquivo .env")
        print_info("2. Adicione: GOOGLE_API_KEY=sua_chave_aqui")
        print_info("3. Obtenha a chave em: https://aistudio.google.com/app/apikey")
        print("="*60 + "\n")
        return 1
    
    # 4. Testar API
    tts_ok = test_tts_api()
    
    print("\n" + "="*60)
    if google_ok and tts_ok:
        print_success("CONFIGURAÇÃO COMPLETA!")
        print_info("O TTS deve funcionar corretamente agora.")
        print_info("Reinicie o servidor Flask para aplicar as mudanças.")
    elif google_ok and not tts_ok:
        print_warning("CHAVE CONFIGURADA, MAS API NÃO HABILITADA")
        print_info("Siga as instruções acima para habilitar a API.")
    else:
        print_error("CONFIGURAÇÃO INCOMPLETA")
    print("="*60 + "\n")
    
    return 0 if (google_ok and tts_ok) else 1

if __name__ == '__main__':
    sys.exit(main())
