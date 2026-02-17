#!/bin/bash

echo "============================================================"
echo "  🔧 Restaurar Emails Autorizados"
echo "============================================================"
echo ""
echo "Este script vai restaurar os 300+ emails autorizados"
echo "a partir do arquivo Excel de vendas."
echo ""
read -p "Pressione Enter para continuar..."

echo ""
echo "⏳ Verificando dependências..."
if ! python3 -c "import pandas, openpyxl" 2>&1; then
    echo "❌ Pandas ou openpyxl não instalados."
    echo "📦 Instalando dependências..."
    if ! pip3 install pandas openpyxl; then
        echo "❌ Erro ao instalar dependências."
        echo "💡 Tente executar manualmente: pip3 install pandas openpyxl"
        exit 1
    fi
fi

echo "✅ Dependências OK!"
echo ""
echo "🔄 Executando script de restauração..."
python3 restore_authorized_emails.py

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "  ✅ Emails restaurados com sucesso!"
    echo "============================================================"
    echo ""
    echo "Próximos passos:"
    echo "1. Inicie o servidor: python3 api/index.py"
    echo "2. Acesse: http://localhost:4004"
    echo "3. Faça login com um email autorizado"
    echo ""
else
    echo ""
    echo "============================================================"
    echo "  ❌ Erro ao restaurar emails"
    echo "============================================================"
    echo ""
    echo "Verifique:"
    echo "- O arquivo sales_aohqw_1768560610634.xlsx existe?"
    echo "- Você tem permissões de escrita no diretório?"
    echo ""
    echo "Leia COMO_RESTAURAR_EMAILS.md para mais detalhes."
    echo ""
fi
