@echo off
chcp 65001 >nul
title Servidor Flask - IA de Conversacao
cls

cd /d "%~dp0"

echo.
echo ============================================================
echo   INICIANDO SERVIDOR FLASK
echo ============================================================
echo.

REM Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado!
    echo Instale Python: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [OK] Python encontrado
echo.

REM Encerrar processos antigos na porta 8912
echo [INFO] Verificando porta 8912...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8912" ^| findstr "LISTENING"') do (
    echo [INFO] Encerrando processo anterior (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo.
echo ============================================================
echo   SERVIDOR INICIANDO...
echo ============================================================
echo.
echo Porta: 8912
echo URL: http://localhost:8912
echo.
echo Aguarde alguns segundos...
echo.
echo ============================================================
echo.

REM Iniciar servidor na mesma janela para ver erros
python api\index.py

pause
