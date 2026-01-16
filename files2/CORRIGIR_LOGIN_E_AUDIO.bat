@echo off
REM ========================================
REM   CORRIGIR LOGIN + ÁUDIO
REM ========================================

echo.
echo ========================================
echo   CORRIGINDO LOGIN E AUDIO
echo ========================================
echo.
echo Este script vai:
echo   1. Restaurar a tela de login
echo   2. Configurar o audio (transcrição + TTS)
echo   3. Criar script de teste
echo.
echo Pressione qualquer tecla para começar...
pause >nul

echo.
echo Executando correções...
python corrigir_login_e_audio.py

echo.
pause
