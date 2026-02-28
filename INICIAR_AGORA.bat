@echo off
chcp 65001 >nul
title Iniciando Servidor - IA de Conversacao
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

REM Encerrar processos antigos na porta 4343
echo [INFO] Verificando porta 4343...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":4343" ^| findstr "LISTENING"') do (
    echo [INFO] Encerrando processo anterior (PID: %%a)...
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo.
echo ============================================================
echo   SERVIDOR INICIANDO...
echo ============================================================
echo.
echo Porta: 4343
echo URL: http://localhost:4343
echo.
echo Aguarde alguns segundos...
echo.
echo ============================================================
echo.

REM Iniciar servidor
start "Flask Server" cmd /k "cd /d %~dp0 && python api\index.py"

timeout /t 5 /nobreak >nul

echo [OK] Servidor iniciado!
echo.
echo Abrindo navegador...
start http://localhost:4343
echo.
echo ============================================================
echo.
echo Servidor rodando em nova janela.
echo Feche esta janela quando quiser.
echo.
pause
