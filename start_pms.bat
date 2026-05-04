@echo off
title AC PMS Launcher
color 0A

cd /d "%~dp0"

echo.
echo  =============================================
echo    AC PMS System — Starting...
echo  =============================================
echo.

:: Kill any old instances
taskkill /f /im streamlit.exe >nul 2>&1
taskkill /f /im ssh.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: Clean old url files
del /f url.txt url_err.txt >nul 2>&1

echo  [1/2] Starting Streamlit app...
start "AC PMS - App" /min cmd /c "cd /d %~dp0 && streamlit run app.py"
timeout /t 5 /nobreak >nul

echo  [2/2] Getting your public URL...
echo.

:: Start tunnel in background, capture output
start /b ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:8501 nokey@localhost.run > url.txt 2> url_err.txt

:: Wait and extract URL then save to DB
timeout /t 15 /nobreak >nul
python get_url.py

echo.
echo  Keep this window open while vendors use the app.
echo  Close it to stop the app.
echo.
pause
