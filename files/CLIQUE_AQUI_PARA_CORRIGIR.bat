@echo off
REM ========================================
REM   CORREÇÃO AUTOMÁTICA - SUPER SIMPLES
REM ========================================

echo.
echo ========================================
echo   CORRIGINDO SEU PROJETO AUTOMATICAMENTE
echo ========================================
echo.
echo Este script vai:
echo   1. Procurar seu projeto automaticamente
echo   2. Criar backup do arquivo original
echo   3. Aplicar a correção
echo   4. Verificar se funcionou
echo.
echo Pressione qualquer tecla para começar...
pause >nul

echo.
echo Executando script Python...
python corrigir_automatico.py

echo.
echo ========================================
echo Pressione qualquer tecla para sair...
pause >nul
