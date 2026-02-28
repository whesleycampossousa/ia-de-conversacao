@echo off
chcp 65001 >nul
title Verificar Servidor - IA de Conversacao
cls
echo.
echo ============================================================
echo   VERIFICANDO SERVIDOR
echo ============================================================
echo.

REM Verificar se porta 8912 está em uso
netstat -an | findstr ":8912" >nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] Porta 8912 esta em uso (servidor provavelmente rodando)
    echo.
    echo Testando conexao...
    curl -s http://localhost:8912 >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [OK] Servidor esta respondendo!
        echo.
        echo Acesse: http://localhost:8912
        echo.
        start http://localhost:8912
    ) else (
        echo [AVISO] Porta em uso mas servidor nao esta respondendo
        echo [INFO] Pode estar ainda inicializando...
    )
) else (
    echo [ERRO] Servidor nao esta rodando!
    echo.
    echo Para iniciar o servidor:
    echo   1. Execute: INICIAR.bat
    echo   2. Ou execute: EXECUTAR_TUDO_AUTOMATICO.bat
    echo.
)

echo.
echo ============================================================
pause
