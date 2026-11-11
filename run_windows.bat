@echo off
setlocal
echo ========================================================
echo   Spoustim S&P 500 Radar & Portfolio Guard
echo ========================================================

REM Kontrola existence virtualniho prostredi
if not exist venv (
    echo Vytvarim virtualni prostredi venv...
    where py >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        py -3 -m venv venv
    ) else (
        python -m venv venv
    )
    call venv\Scripts\activate
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate
)

REM Spusteni aplikace
streamlit run app.py
pause
