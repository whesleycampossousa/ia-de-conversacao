@echo off
chcp 65001 >nul
title Iniciar Servidor - IA de Conversacao
cls
cd /d "%~dp0"

echo.
echo ============================================================
echo   INICIANDO SERVIDOR
echo ============================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado!
    pause
    exit /b 1
)

REM Verificar se porta está em uso
netstat -an | findstr ":8912" >nul
if %ERRORLEVEL% EQU 0 (
    echo [AVISO] Porta 8912 ja esta em uso!
    echo Encerrando processo anterior...
    for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8912" ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

echo [INFO] Iniciando servidor na porta 8912...
echo [INFO] Acesse: http://localhost:8912
echo.
echo Pressione Ctrl+C para parar o servidor
echo.
echo ============================================================
echo.

python api\index.py

pause
