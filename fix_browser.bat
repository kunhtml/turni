@echo off
echo ========================================
echo Fix Playwright Browser Error
echo ========================================
echo.

echo [1/3] Installing Playwright browsers...
python -m playwright install chromium firefox --with-deps

echo.
echo [2/3] Verifying installation...
python -m playwright --version

echo.
echo [3/3] Installation complete!
echo.
echo ========================================
echo Next Steps:
echo ========================================
echo 1. If successful, run: python main.py
echo 2. If still fails, see FIX_BROWSER_ERROR.md
echo ========================================
pause
