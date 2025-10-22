@echo off
chcp 65001 > nul
title Turnitin Bot - Auto Setup & Run
color 0A

echo.
echo ================================================
echo     TURNITIN BOT - AUTO SETUP & RUN
echo ================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [OK] Found %PYTHON_VERSION%
echo.

REM Check if pip is available
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip is not available
    pause
    exit /b 1
)

echo [OK] pip is available
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo [SETUP] Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
    echo.
)

REM Activate virtual environment
echo [SETUP] Activating virtual environment...
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated
echo.

REM Check and install requirements
echo [SETUP] Checking dependencies...
pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    echo Trying again with verbose output...
    pip install -r requirements.txt
    pause
    exit /b 1
)
echo [OK] All dependencies installed
echo.

REM Install Playwright browsers
echo [SETUP] Installing Playwright browsers...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [WARNING] Playwright browser installation encountered issues
    echo Continuing anyway...
    echo.
)
echo [OK] Playwright setup complete
echo.

REM Check if .env file exists
if not exist ".env" (
    echo [WARNING] .env file not found!
    echo Please create .env file with required configuration
    echo Required variables:
    echo   - TELEGRAM_BOT_TOKEN
    echo   - ADMIN_TELEGRAM_ID
    echo   - TURNITIN_EMAIL
    echo   - TURNITIN_PASSWORD
    echo.
    pause
    exit /b 1
)

echo [OK] .env file found
echo.

REM Final check - verify main.py exists
if not exist "main.py" (
    echo [ERROR] main.py not found in current directory
    pause
    exit /b 1
)

echo [OK] main.py found
echo.

REM Display startup info
echo ================================================
echo     STARTING TURNITIN BOT
echo ================================================
echo.
echo Bot Configuration:
echo   - Python: %PYTHON_VERSION%
echo   - Virtual Environment: Active
echo   - Dependencies: Installed
echo   - Playwright: Ready
echo.
echo Press Ctrl+C to stop the bot
echo.
timeout /t 3 /nobreak

REM Run the bot
python main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Bot crashed with error code %errorlevel%
    pause
)

pause
