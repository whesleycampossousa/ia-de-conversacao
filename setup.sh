#!/bin/bash
# Script de Setup para IA de Conversação

echo "========================================"
echo "   Setup - IA de Conversação"
echo "========================================"
echo ""

# Verificar se .env existe
if [ ! -f ".env" ]; then
    echo "[ERRO] Arquivo .env não encontrado!"
    echo "Por favor, configure o arquivo .env primeiro."
    exit 1
fi

echo "[1/4] Verificando dependências..."
if ! command -v python3 &> /dev/null; then
    echo "[ERRO] Python não encontrado! Instale o Python primeiro."
    exit 1
fi

echo "[2/4] Instalando dependências..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "[ERRO] Falha ao instalar dependências!"
    exit 1
fi

echo ""
echo "[3/4] Verificando configuração do .env..."
if grep -q "GOOGLE_API_KEY=your_api_key_here" .env; then
    echo ""
    echo "========================================"
    echo "   [!] ATENÇÃO: API Key não configurada!"
    echo "========================================"
    echo ""
    echo "Você precisa obter sua API Key do Gemini:"
    echo "1. Acesse: https://aistudio.google.com/app/apikey"
    echo "2. Faça login com sua conta Google"
    echo "3. Clique em 'Create API Key'"
    echo "4. Copie a chave e substitua em .env"
    echo ""
    echo "Abrindo o site..."
    if command -v xdg-open &> /dev/null; then
        xdg-open "https://aistudio.google.com/app/apikey"
    elif command -v open &> /dev/null; then
        open "https://aistudio.google.com/app/apikey"
    fi
    echo ""
    echo "Após configurar a API Key, execute este script novamente."
    exit 1
fi

echo "[4/4] Configuração OK!"
echo ""
echo "========================================"
echo "   Tudo pronto para rodar!"
echo "========================================"
echo ""
echo "Para iniciar o servidor local:"
echo "  python3 api/index.py"
echo ""
echo "Depois acesse: http://localhost:4004"
echo ""
echo "Para fazer deploy no Vercel:"
echo "  vercel --prod"
echo ""
