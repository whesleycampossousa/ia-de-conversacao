@echo off
REM Monitor Launcher for Windows Task Scheduler
REM Runs the monitoring system and opens HTML report on critical failure

cd /d "C:\Users\whesl\OneDrive\Documentos\Projetos\_Projetos_Ativos\IA de conversação"

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Run monitor for all environments
python monitor\monitor_app.py --all-envs

REM Capture exit code
set EXITCODE=%ERRORLEVEL%

REM Log based on result
if %EXITCODE% GEQ 2 (
    echo [%date% %time%] CRITICAL FAILURE DETECTED >> monitor_errors.log
    REM HTML will auto-open due to config setting
    exit /b 2
)

if %EXITCODE% EQU 1 (
    echo [%date% %time%] Warnings detected >> monitor_warnings.log
    exit /b 1
)

echo [%date% %time%] All checks passed >> monitor_success.log
exit /b 0
