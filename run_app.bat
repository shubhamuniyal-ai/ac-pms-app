@echo off
cd /d "%~dp0"
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting AC PMS App...
streamlit run app.py
pause