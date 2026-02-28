@echo off
chcp 65001 >nul
echo ========================================
echo   INSTALANDO PYDUB PARA COMBINAR AUDIOS
echo ========================================
echo.
echo Isso vai instalar a biblioteca pydub
echo necessaria para combinar audios bilinguais.
echo.
pause

pip install pydub

echo.
echo ========================================
echo   INSTALACAO CONCLUIDA
echo ========================================
echo.
echo NOTA: pydub precisa do ffmpeg para MP3.
echo Se nao funcionar, o sistema usara concatenacao simples.
echo.
pause
