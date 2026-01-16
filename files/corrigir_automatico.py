"""
Script para localizar e corrigir automaticamente o arquivo index.py
"""
import os
import shutil
from pathlib import Path

def find_project_folder():
    """Localiza a pasta do projeto procurando por api/index.py"""
    print("🔍 Procurando o projeto...")
    
    # Locais comuns para projetos
    search_paths = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path.home(),
        Path("C:/Users").expanduser() if os.name == 'nt' else Path.home(),
    ]
    
    for base_path in search_paths:
        if not base_path.exists():
            continue
            
        print(f"   Procurando em: {base_path}")
        
        # Procurar recursivamente (até 5 níveis de profundidade)
        for root, dirs, files in os.walk(base_path):
            # Limitar profundidade
            depth = root.replace(str(base_path), '').count(os.sep)
            if depth > 5:
                continue
                
            # Verificar se tem a estrutura api/index.py
            if 'api' in dirs:
                api_path = Path(root) / 'api' / 'index.py'
                if api_path.exists():
                    # Verificar se é o projeto correto (tem scenarios_db.json)
                    if (Path(root) / 'scenarios_db.json').exists():
                        print(f"✅ Projeto encontrado: {root}")
                        return Path(root)
    
    return None

def apply_fix(project_path, fixed_file_path):
    """Aplica a correção no arquivo"""
    print("\n🔧 Aplicando correção...")
    
    # Caminhos
    original_file = project_path / 'api' / 'index.py'
    backup_file = project_path / 'api' / 'index.py.backup'
    
    # Criar backup
    print(f"   Criando backup: {backup_file}")
    shutil.copy2(original_file, backup_file)
    print("   ✅ Backup criado")
    
    # Copiar arquivo corrigido
    print(f"   Copiando arquivo corrigido para: {original_file}")
    shutil.copy2(fixed_file_path, original_file)
    print("   ✅ Arquivo substituído")
    
    # Verificar sintaxe
    print("   Verificando sintaxe Python...")
    import py_compile
    try:
        py_compile.compile(str(original_file), doraise=True)
        print("   ✅ Sintaxe válida!")
        return True
    except py_compile.PyCompileError as e:
        print(f"   ❌ Erro de sintaxe: {e}")
        print("   Restaurando backup...")
        shutil.copy2(backup_file, original_file)
        return False

def main():
    print("="*60)
    print("   SCRIPT DE CORREÇÃO AUTOMÁTICA")
    print("="*60)
    print()
    
    # Localizar projeto
    project_path = find_project_folder()
    
    if not project_path:
        print("\n❌ Projeto não encontrado!")
        print("\nPor favor, informe o caminho manualmente:")
        print("Exemplo: C:\\Users\\SeuNome\\Documents\\MeuProjeto")
        project_input = input("\nCaminho do projeto: ").strip()
        
        if project_input:
            project_path = Path(project_input)
            if not (project_path / 'api' / 'index.py').exists():
                print("❌ Arquivo api/index.py não encontrado neste caminho!")
                return
        else:
            return
    
    # Caminho do arquivo corrigido (deve estar no mesmo diretório do script)
    script_dir = Path(__file__).parent
    fixed_file = script_dir / 'index.py'
    
    if not fixed_file.exists():
        print(f"\n❌ Arquivo corrigido não encontrado: {fixed_file}")
        print("\nPor favor, coloque o arquivo index.py corrigido na mesma pasta deste script.")
        return
    
    print(f"\n📂 Projeto: {project_path}")
    print(f"📄 Arquivo corrigido: {fixed_file}")
    
    # Confirmar
    print("\n⚠️  ATENÇÃO: O arquivo api/index.py será substituído.")
    print("   Um backup será criado automaticamente.")
    response = input("\nDeseja continuar? (s/n): ").strip().lower()
    
    if response != 's':
        print("Operação cancelada.")
        return
    
    # Aplicar correção
    if apply_fix(project_path, fixed_file):
        print("\n" + "="*60)
        print("   ✅ CORREÇÃO APLICADA COM SUCESSO!")
        print("="*60)
        print(f"\n📁 Backup salvo em: {project_path / 'api' / 'index.py.backup'}")
        print(f"\n🚀 Próximos passos:")
        print(f"   1. Abra o terminal na pasta: {project_path}")
        print(f"   2. Execute: python api/index.py")
        print(f"   3. Acesse: http://localhost:4004")
    else:
        print("\n❌ Falha ao aplicar correção!")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperação cancelada pelo usuário.")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()
    
    input("\nPressione ENTER para sair...")
