@echo off
title OrderFlow Server
echo ========================================================
echo   Starting OrderFlow Web Application
echo   Customer, Item & Order Management (MySQL)
echo ========================================================
echo.

:: Check python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ and try again.
    pause
    exit /b 1
)

:: Run seed data if first time
if not exist "data\db_store.json" (
    echo [INFO] Running initial seed data setup...
    python seed_data.py
    echo.
)

echo [INFO] Starting web application server...
echo [INFO] Open your browser and navigate to: http://localhost:5000
echo.
python app.py 5000
pause
