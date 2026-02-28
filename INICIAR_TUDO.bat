@echo off
chcp 65001 >nul
title Iniciar Servidor Flask - IA de Conversacao
echo ========================================
echo   INICIANDO SERVIDOR FLASK
echo ========================================
echo.
echo Porta: 8912
echo URL: http://localhost:8912
echo.
echo Pressione Ctrl+C para parar o servidor
echo.
echo ========================================
echo.

python api\index.py

pause
