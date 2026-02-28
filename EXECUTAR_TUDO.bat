@echo off
chcp 65001 >nul
title Configuracao Automatica - IA de Conversacao
cls
echo.
echo ============================================================
echo   CONFIGURACAO AUTOMATICA COMPLETA
echo ============================================================
echo.

REM Verificar se Python está instalado
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado!
    echo Instale Python primeiro.
    pause
    exit /b 1
)

REM Mudar para o diretório do script
cd /d "%~dp0"

REM 1. Testar TTS
echo [1/4] Testando configuracao do TTS...
echo.
python testar_tts_automatico.py
set TTS_OK=%ERRORLEVEL%

if %TTS_OK% NEQ 0 (
    echo.
    echo ============================================================
    echo   API DO TTS NAO ESTA HABILITADA
    echo ============================================================
    echo.
    echo Abrindo console do Google Cloud automaticamente...
    echo.
    start https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
    echo.
    echo INSTRUCOES (1 minuto):
    echo   1. Faca login com sua conta Google
    echo   2. Clique no botao "ATIVAR" ou "ENABLE"
    echo   3. Aguarde 10-30 segundos
    echo   4. Execute este script novamente: EXECUTAR_TUDO.bat
    echo.
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo [2/4] Verificando se servidor Flask esta rodando...
netstat -an | findstr ":8912" >nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Servidor Flask ja esta rodando na porta 8912
) else (
    echo [INFO] Servidor Flask nao esta rodando
    echo.
    echo [3/4] Iniciando servidor Flask em nova janela...
    start "Flask Server - Porta 8912" cmd /k "cd /d %~dp0 && python api\index.py"
    echo [OK] Servidor Flask iniciado!
    echo [INFO] Aguardando servidor inicializar...
    timeout /t 5 /nobreak >nul
    echo [INFO] Abrindo navegador...
    start http://localhost:8912
)

echo.
echo [4/4] Verificando se servidor esta respondendo...
curl -s http://localhost:8912 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Servidor Flask esta respondendo!
) else (
    echo [AVISO] Servidor pode estar ainda inicializando...
    echo [INFO] Aguarde mais alguns segundos
)

echo.
echo ============================================================
echo   CONFIGURACAO COMPLETA!
echo ============================================================
echo.
echo Servidor Flask: http://localhost:8912
echo.
echo Pronto para usar! Acesse a URL acima no navegador.
echo.
echo ============================================================
pause
