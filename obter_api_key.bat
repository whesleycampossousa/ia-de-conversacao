@echo off
REM Script para abrir o site do Google AI Studio
echo Abrindo Google AI Studio para obter API Key...
start https://aistudio.google.com/app/apikey
echo.
echo ========================================
echo Passos para obter a API Key:
echo ========================================
echo 1. Faca login com sua conta Google
echo 2. Clique em "Create API Key"
echo 3. Copie a chave gerada
echo 4. Abra o arquivo .env
echo 5. Substitua "your_api_key_here" pela chave copiada
echo.
echo Depois execute: setup.bat
echo ========================================
pause
