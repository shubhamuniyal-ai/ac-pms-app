@echo off
title Push PMS App to GitHub
color 0A

cd /d "%~dp0"

echo.
echo  ============================================
echo    AC PMS — Push to GitHub
echo  ============================================
echo.
echo  You need a GitHub account.
echo  If you don't have one, go to: https://github.com/signup
echo.
set /p GITHUB_USER=Enter your GitHub username:
set /p REPO_NAME=Enter repository name (e.g. ac-pms-app):

echo.
echo  Setting up Git...

set GIT=C:\Program Files\Git\cmd\git.exe
if not exist "%GIT%" set GIT=git

"%GIT%" config --global user.email "admin@pms.local"
"%GIT%" config --global user.name "PMS Admin"
"%GIT%" init
"%GIT%" add .
"%GIT%" commit -m "Initial AC PMS deployment"
"%GIT%" branch -M main
"%GIT%" remote remove origin 2>nul
"%GIT%" remote add origin https://github.com/%GITHUB_USER%/%REPO_NAME%.git

echo.
echo  Pushing to GitHub...
echo  (A browser or password prompt may appear — login with your GitHub account)
echo.
"%GIT%" push -u origin main

echo.
echo  ============================================
echo   DONE! Code is now on GitHub.
echo  ============================================
echo.
echo  Next step: Deploy on Railway
echo   1. Go to https://railway.app
echo   2. Sign in with GitHub
echo   3. Click "New Project" then "Deploy from GitHub repo"
echo   4. Select: %GITHUB_USER%/%REPO_NAME%
echo   5. After deploy, go to Settings and add Volume at path: /app/data
echo   6. Set environment variable: DATA_DIR = /app/data
echo   7. Your permanent URL will be shown in the Railway dashboard
echo.
pause
