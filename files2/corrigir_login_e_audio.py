#!/usr/bin/env python3
"""
Script para corrigir automaticamente:
1. Restaurar página de login
2. Configurar áudio (Groq + Google TTS)
"""
import os
import re
from pathlib import Path

def fix_login_page(project_path):
    """Corrige a rota raiz para servir login.html"""
    print("\n🔧 Corrigindo página de login...")
    
    index_file = project_path / 'api' / 'index.py'
    
    # Ler conteúdo
    with open(index_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Fazer backup
    backup_file = project_path / 'api' / 'index.py.backup2'
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"   ✅ Backup criado: {backup_file}")
    
    # Substituir scenarios.html por login.html na rota raiz
    original = content
    content = re.sub(
        r"return send_file\(os\.path\.join\(BASE_DIR, 'scenarios\.html'\)\)",
        r"return send_file(os.path.join(BASE_DIR, 'login.html'))",
        content
    )
    content = re.sub(
        r'"Error serving scenarios\.html:',
        r'"Error serving login.html:',
        content
    )
    
    if content != original:
        # Salvar alterações
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(content)
        print("   ✅ Página de login restaurada")
        print("   → Rota '/' agora serve login.html")
        return True
    else:
        print("   ⚠️  Nenhuma alteração necessária (já está correto)")
        return False

def setup_audio_keys(project_path):
    """Configura as chaves de API para áudio"""
    print("\n🔊 Configurando áudio...")
    
    env_file = project_path / '.env'
    
    if not env_file.exists():
        print("   ❌ Arquivo .env não encontrado!")
        return False
    
    # Ler .env
    with open(env_file, 'r', encoding='utf-8') as f:
        env_content = f.read()
    
    # Verificar se já tem GROQ_API_KEY
    has_groq = 'GROQ_API_KEY' in env_content
    
    if has_groq:
        print("   ✅ GROQ_API_KEY já está no .env")
    else:
        print("   ⚠️  GROQ_API_KEY não encontrada no .env")
        print("\n   Para adicionar:")
        print("   1. Acesse: https://console.groq.com/keys")
        print("   2. Faça login e crie uma API Key")
        print("   3. Adicione no .env:")
        print("      GROQ_API_KEY=sua_chave_aqui")
        
        # Perguntar se quer adicionar agora
        print("\n   Deseja adicionar agora? (s/n): ", end='')
        try:
            response = input().strip().lower()
            if response == 's':
                print("   Cole a chave Groq: ", end='')
                groq_key = input().strip()
                
                if groq_key:
                    # Adicionar ao .env
                    env_content += f"\n# Groq Whisper para transcrição\nGROQ_API_KEY={groq_key}\n"
                    
                    with open(env_file, 'w', encoding='utf-8') as f:
                        f.write(env_content)
                    
                    print("   ✅ GROQ_API_KEY adicionada ao .env")
                else:
                    print("   ⚠️  Chave vazia, pulando...")
        except:
            print("   ⚠️  Entrada cancelada")
    
    print("\n   📝 Verificando Google Cloud TTS...")
    print("   → Certifique-se de habilitar a API:")
    print("   → https://console.cloud.google.com/apis/library/texttospeech.googleapis.com")
    
    return True

def create_test_script(project_path):
    """Cria script de teste de áudio"""
    print("\n🧪 Criando script de teste...")
    
    test_script = project_path / 'testar_audio.py'
    
    script_content = '''#!/usr/bin/env python3
import os
from dotenv import load_dotenv

load_dotenv()

print("="*60)
print("   TESTE DE CONFIGURAÇÃO DE ÁUDIO")
print("="*60)
print()

# Testar Groq
groq_key = os.getenv("GROQ_API_KEY")
if groq_key:
    print("✅ GROQ_API_KEY: Configurada")
    print(f"   Primeiros caracteres: {groq_key[:15]}...")
else:
    print("❌ GROQ_API_KEY: FALTANDO")
    print("   Adicione no .env: GROQ_API_KEY=sua_chave")

print()

# Testar Google
google_key = os.getenv("GOOGLE_API_KEY")
if google_key:
    print("✅ GOOGLE_API_KEY: Configurada")
    print(f"   Primeiros caracteres: {google_key[:15]}...")
else:
    print("❌ GOOGLE_API_KEY: FALTANDO")
    print("   Adicione no .env: GOOGLE_API_KEY=sua_chave")

print()
print("="*60)

if groq_key and google_key:
    print("✅ CONFIGURAÇÃO OK - Áudio deve funcionar!")
    print()
    print("Próximos passos:")
    print("1. Certifique-se de habilitar Google Cloud TTS API")
    print("2. Reinicie o servidor: python api/index.py")
    print("3. Permita acesso ao microfone no navegador")
else:
    print("❌ CONFIGURAÇÃO INCOMPLETA")
    print("   Siga as instruções no arquivo FIX_AUDIO_COMPLETO.md")

print("="*60)
'''
    
    with open(test_script, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print(f"   ✅ Script criado: {test_script}")
    print("   Execute: python testar_audio.py")
    
    return True

def main():
    print("="*60)
    print("   CORREÇÃO AUTOMÁTICA - LOGIN + ÁUDIO")
    print("="*60)
    
    # Encontrar projeto
    script_dir = Path(__file__).parent
    
    # Procurar api/index.py
    if (script_dir / 'api' / 'index.py').exists():
        project_path = script_dir
    else:
        # Procurar no diretório pai
        parent = script_dir.parent
        if (parent / 'api' / 'index.py').exists():
            project_path = parent
        else:
            print("\n❌ Projeto não encontrado!")
            print("Execute este script na pasta do projeto.")
            return
    
    print(f"\n📂 Projeto: {project_path}")
    
    # Aplicar correções
    login_fixed = fix_login_page(project_path)
    audio_setup = setup_audio_keys(project_path)
    test_created = create_test_script(project_path)
    
    # Resumo
    print("\n" + "="*60)
    print("   RESUMO")
    print("="*60)
    
    if login_fixed:
        print("✅ Página de login restaurada")
    else:
        print("⚠️  Página de login não precisou de correção")
    
    if audio_setup:
        print("✅ Configuração de áudio verificada")
    
    if test_created:
        print("✅ Script de teste criado")
    
    print("\n" + "="*60)
    print("   PRÓXIMOS PASSOS")
    print("="*60)
    print("\n1. Configure as chaves de API (se ainda não fez):")
    print("   → Groq: https://console.groq.com/keys")
    print("   → Habilitar TTS: https://console.cloud.google.com/apis/library/texttospeech.googleapis.com")
    print("\n2. Teste a configuração:")
    print("   → python testar_audio.py")
    print("\n3. Reinicie o servidor:")
    print("   → python api/index.py")
    print("\n4. Acesse:")
    print("   → http://localhost:4004")
    print("\n5. Se o áudio não funcionar, consulte:")
    print("   → FIX_AUDIO_COMPLETO.md")
    print("\n" + "="*60)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperação cancelada.")
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
    
    input("\nPressione ENTER para sair...")
