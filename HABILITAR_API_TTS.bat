@echo off
chcp 65001 >nul
echo ========================================
echo   HABILITAR API TEXT-TO-SPEECH
echo ========================================
echo.
echo Abrindo o console do Google Cloud...
echo.
echo INSTRUCOES:
echo 1. Faca login com sua conta Google
echo 2. Clique em "ATIVAR" ou "ENABLE"
echo 3. Aguarde 1-2 minutos
echo 4. Reinicie o servidor Flask
echo.
echo ========================================
start https://console.cloud.google.com/apis/library/texttospeech.googleapis.com
echo.
pause
