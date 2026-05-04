@echo off
title AC PMS Launcher
color 0A
echo.
echo  =============================================
echo    AC PMS System — Starting
echo  =============================================
echo.

cd /d "%~dp0"

echo  [1/2] Starting Streamlit app...
start "AC PMS - App" cmd /k "cd /d %~dp0 && streamlit run app.py"

timeout /t 4 /nobreak >nul

echo  [2/2] Starting public internet tunnel...
echo.
start "AC PMS - Public URL" cmd /k "cd /d %~dp0 && python tunnel.py"

echo.
echo  Two windows have opened:
echo   - "AC PMS - App"        : the local Streamlit server
echo   - "AC PMS - Public URL" : shows the internet URL for vendors
echo.
echo  Share the PUBLIC URL with vendors and users.
echo  Keep both windows open while the app is in use.
echo.
pause
