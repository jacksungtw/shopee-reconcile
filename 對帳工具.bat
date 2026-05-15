@echo off
title Shopee Reconcile Tool

cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

REM Auto-detect Python
set PY_CMD=
if exist "%LOCALAPPDATA%\Programs\Python\Launcher\py.exe" set PY_CMD=%LOCALAPPDATA%\Programs\Python\Launcher\py.exe
if "%PY_CMD%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set PY_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe
if "%PY_CMD%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if "%PY_CMD%"=="" if exist "C:\Program Files\Python313\python.exe" set PY_CMD=C:\Program Files\Python313\python.exe
if "%PY_CMD%"=="" if exist "C:\Python313\python.exe" set PY_CMD=C:\Python313\python.exe
if "%PY_CMD%"=="" (
    where py >nul 2>nul
    if not errorlevel 1 set PY_CMD=py
)
if "%PY_CMD%"=="" (
    where python >nul 2>nul
    if not errorlevel 1 set PY_CMD=python
)

if "%PY_CMD%"=="" (
    echo.
    echo === ERROR: Python not found ===
    echo.
    echo Install Python from https://www.python.org/downloads/
    echo Then run: pip install pandas openpyxl msoffcrypto-tool
    echo.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo.
    echo === Shopee Reconciliation Tool ===
    echo.
    echo Drag Order.completed Excel files onto this .bat
    echo.
    pause
    exit /b 0
)

%PY_CMD% "%~dp0shopee_reconcile.py" %*

if errorlevel 1 (
    echo.
    echo [ERROR] Execution failed. See messages above.
    pause
) else (
    echo.
    echo Done! Reports are in the same folder as your Excel files.
    pause
)
