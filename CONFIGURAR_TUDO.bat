@echo off
chcp 65001 >nul
echo ========================================
echo   CONFIGURACAO AUTOMATICA COMPLETA
echo ========================================
echo.

REM Testar TTS
echo [1/3] Testando configuração do TTS...
python testar_tts_automatico.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERRO: API do TTS nao esta funcionando!
    echo.
    echo Abrindo console do Google Cloud para habilitar a API...
    start https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
    echo.
    echo INSTRUCOES:
    echo 1. Faca login
    echo 2. Clique em "ATIVAR"
    echo 3. Aguarde 1-2 minutos
    echo 4. Execute este script novamente
    echo.
    pause
    exit /b 1
)

echo.
echo [2/3] Verificando se o servidor Flask esta rodando...
netstat -an | findstr ":8912" >nul
if %ERRORLEVEL% EQU 0 (
    echo Servidor Flask ja esta rodando na porta 8912
) else (
    echo Servidor Flask nao esta rodando
    echo.
    echo [3/3] Iniciando servidor Flask...
    echo.
    start "Flask Server" cmd /k "python api\index.py"
    echo Aguardando servidor iniciar...
    timeout /t 3 /nobreak >nul
    echo Servidor Flask iniciado!
)

echo.
echo ========================================
echo   CONFIGURACAO COMPLETA!
echo ========================================
echo.
echo Acesse: http://localhost:8912
echo.
pause
