@echo off
setlocal
echo ========================================================
echo   Spoustim ranni sken S&P 500 a MidCap 400
echo ========================================================

if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe scanner.py --mode full
) else (
    py -3 scanner.py --mode full
)
