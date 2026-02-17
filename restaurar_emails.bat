@echo off
echo ============================================================
echo   🔧 Restaurar Emails Autorizados
echo ============================================================
echo.
echo Este script vai restaurar os 300+ emails autorizados
echo a partir do arquivo Excel de vendas.
echo.
pause

echo.
echo ⏳ Verificando dependencias...
python -c "import pandas, openpyxl" 2>nul
if %errorlevel% neq 0 (
    echo ❌ Pandas ou openpyxl nao instalados.
    echo 📦 Instalando dependencias...
    pip install pandas openpyxl
    if %errorlevel% neq 0 (
        echo ❌ Erro ao instalar dependencias.
        echo 💡 Tente executar manualmente: pip install pandas openpyxl
        pause
        exit /b 1
    )
)

echo ✅ Dependencias OK!
echo.
echo 🔄 Executando script de restauracao...
python restore_authorized_emails.py

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo   ✅ Emails restaurados com sucesso!
    echo ============================================================
    echo.
    echo Proximos passos:
    echo 1. Inicie o servidor: python api/index.py
    echo 2. Acesse: http://localhost:4004
    echo 3. Faca login com um email autorizado
    echo.
) else (
    echo.
    echo ============================================================
    echo   ❌ Erro ao restaurar emails
    echo ============================================================
    echo.
    echo Verifique:
    echo - O arquivo sales_aohqw_1768560610634.xlsx existe?
    echo - Voce tem permissoes de escrita no diretorio?
    echo.
    echo Leia COMO_RESTAURAR_EMAILS.md para mais detalhes.
    echo.
)

pause
