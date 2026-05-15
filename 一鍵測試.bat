@echo off
title Reconcile Tool - One-click Test

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
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   One-click Test
echo ============================================
echo.

REM Step 1: Generate test data
echo [1/3] Generating test data...
%PY_CMD% gen_test_data.py
if errorlevel 1 (
    echo [ERROR] Test data generation failed.
    pause
    exit /b 1
)
echo [OK] Test data ready.
echo.

REM Step 2: Run reconciliation
echo [2/3] Running reconciliation...
%PY_CMD% shopee_reconcile.py "_test_data\Order.completed.20260301_20260331.xlsx"
if errorlevel 1 (
    echo [ERROR] Reconciliation failed.
    pause
    exit /b 1
)
echo.
echo [OK] Done!
echo.

REM Step 3: Open output folder
echo [3/3] Opening output folder...
echo.
echo Output files in: _test_data\
echo   - 對帳表_115年3月.xlsx
echo   - 差異日明細_115年3月.xlsx
echo   - 工程師獎金_115年3月.xlsx
echo.
start "" "_test_data"
echo.
echo ============================================
echo   Test complete!
echo ============================================
echo.

pause
