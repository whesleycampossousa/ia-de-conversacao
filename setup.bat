@echo off
REM Script de Setup para IA de Conversação
echo ========================================
echo   Setup - IA de Conversacao
echo ========================================
echo.

REM Verificar se .env existe
if not exist ".env" (
    echo [ERRO] Arquivo .env nao encontrado!
    echo Por favor, configure o arquivo .env primeiro.
    pause
    exit /b 1
)

echo [1/4] Verificando dependencias...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao encontrado! Instale o Python primeiro.
    pause
    exit /b 1
)

echo [2/4] Instalando dependencias...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias!
    pause
    exit /b 1
)

echo.
echo [3/4] Verificando configuracao do .env...
findstr /C:"GOOGLE_API_KEY=your_api_key_here" .env >nul
if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   [!] ATENCAO: API Key nao configurada!
    echo ========================================
    echo.
    echo Voce precisa obter sua API Key do Gemini:
    echo 1. Acesse: https://aistudio.google.com/app/apikey
    echo 2. Faca login com sua conta Google
    echo 3. Clique em "Create API Key"
    echo 4. Copie a chave e substitua em .env
    echo.
    echo Pressione qualquer tecla para abrir o site...
    pause >nul
    start https://aistudio.google.com/app/apikey
    echo.
    echo Apos configurar a API Key, execute este script novamente.
    pause
    exit /b 1
)

echo [4/4] Configuracao OK!
echo.
echo ========================================
echo   Tudo pronto para rodar!
echo ========================================
echo.
echo Para iniciar o servidor local:
echo   python api/index.py
echo.
echo Depois acesse: http://localhost:4004
echo.
echo Para fazer deploy no Vercel:
echo   vercel --prod
echo.
pause
