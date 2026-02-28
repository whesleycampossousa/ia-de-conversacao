@echo off
chcp 65001 >nul
title Configuracao e Inicio Automatico - IA de Conversacao
cls
echo.
echo ============================================================
echo   CONFIGURACAO E INICIO AUTOMATICO
echo ============================================================
echo.

REM Mudar para o diretório do script
cd /d "%~dp0"

REM Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado!
    echo Instale Python primeiro: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/5] Verificando Python... [OK]
echo.

REM Instalar/atualizar dependências
echo [2/5] Verificando dependencias...
python -c "import flask" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Instalando dependencias...
    pip install -r requirements.txt --quiet
    if %ERRORLEVEL% NEQ 0 (
        echo [ERRO] Falha ao instalar dependencias!
        pause
        exit /b 1
    )
    echo [OK] Dependencias instaladas
) else (
    echo [OK] Dependencias ja instaladas
)
echo.

REM Verificar .env
echo [3/5] Verificando arquivo .env...
if not exist .env (
    echo [AVISO] Arquivo .env nao encontrado!
    if exist .env.example (
        echo [INFO] Copiando .env.example para .env...
        copy .env.example .env >nul
        echo [OK] Arquivo .env criado
        echo [AVISO] Configure suas API keys no arquivo .env
    ) else (
        echo [ERRO] Arquivo .env.example nao encontrado!
    )
) else (
    echo [OK] Arquivo .env encontrado
)
echo.

REM Verificar se servidor já está rodando
echo [4/5] Verificando servidor...
netstat -an | findstr ":8912" >nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Servidor ja esta rodando na porta 8912
    echo [INFO] Acesse: http://localhost:8912
    echo.
    echo Deseja reiniciar o servidor? (S/N)
    set /p RESPOSTA=
    if /i "%RESPOSTA%"=="S" (
        echo Encerrando servidor anterior...
        for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8912" ^| findstr "LISTENING"') do (
            taskkill /F /PID %%a >nul 2>&1
        )
        timeout /t 2 /nobreak >nul
        echo [OK] Servidor anterior encerrado
    ) else (
        echo [INFO] Mantendo servidor atual
        start http://localhost:8912
        pause
        exit /b 0
    )
) else (
    echo [OK] Porta 8912 disponivel
)
echo.

REM Iniciar servidor em nova janela
echo [5/5] Iniciando servidor Flask...
start "Flask Server - Porta 8912" cmd /k "cd /d %~dp0 && python api\index.py"
echo [OK] Servidor iniciado em nova janela
echo.

REM Aguardar servidor inicializar
echo [INFO] Aguardando servidor inicializar...
timeout /t 5 /nobreak >nul

REM Verificar se servidor está respondendo
echo [INFO] Verificando se servidor esta respondendo...
curl -s http://localhost:8912 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Servidor esta respondendo!
) else (
    echo [AVISO] Servidor pode estar ainda inicializando...
    echo [INFO] Aguarde mais alguns segundos
    timeout /t 3 /nobreak >nul
)

echo.
echo ============================================================
echo   CONFIGURACAO COMPLETA!
echo ============================================================
echo.
echo Servidor Flask: http://localhost:8912
echo.
echo Abrindo navegador...
start http://localhost:8912
echo.
echo ============================================================
echo.
echo Pressione qualquer tecla para fechar esta janela
echo (O servidor continuara rodando na outra janela)
pause >nul
