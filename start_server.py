#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script para iniciar o servidor Flask"""
import os
import sys

# Muda para o diretório do projeto
os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("\n" + "="*60)
print("  INICIANDO SERVIDOR FLASK")
print("="*60)
print(f"\n  Diretório: {os.getcwd()}")
print(f"  Porta: 8912")
print(f"  URL: http://localhost:8912")
print("\n" + "="*60 + "\n")

try:
    # Importa e executa o servidor
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from api.index import app
    
    print("  Servidor iniciando...\n")
    app.run(debug=True, port=8912, host='0.0.0.0', use_reloader=False)
except KeyboardInterrupt:
    print("\n\n  Servidor encerrado pelo usuário.")
    sys.exit(0)
except Exception as e:
    print(f"\n\n  [ERRO] Falha ao iniciar servidor: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
