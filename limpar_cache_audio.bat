@echo off
chcp 65001 >nul
echo ========================================
echo   LIMPANDO CACHE DE AUDIO
echo ========================================
echo.
echo Isso vai remover todos os arquivos de cache de audio
echo para forcar a geracao de novas vozes.
echo.
pause

if exist "audio_cache\common_phrases\*.mp3" (
    echo Limpando cache de frases comuns...
    del /q "audio_cache\common_phrases\*.mp3"
)

if exist "audio_cache\dynamic\*.mp3" (
    echo Limpando cache dinamico...
    del /q "audio_cache\dynamic\*.mp3"
)

echo.
echo Cache limpo! Agora cada voz sera gerada novamente.
echo.
pause
