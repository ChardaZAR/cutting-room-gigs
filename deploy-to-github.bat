@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo   Deploying Cutting Room Gigs to ChardaZAR/cutting-room-gigs
echo ========================================================
echo.

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git is not installed or not in your PATH.
    echo Download Git from https://git-scm.com/download/win
    pause
    exit /b 1
)

if not exist ".git" (
    echo Initializing local Git repository...
    git init
)

:: Ensure OneDrive folder is marked safe and git identity is configured
git config --global --add safe.directory "%cd%" 2>nul
git config user.name >nul 2>nul
if %errorlevel% neq 0 (
    echo Setting local Git author name to ChardaZAR...
    git config user.name "ChardaZAR"
)
git config user.email >nul 2>nul
if %errorlevel% neq 0 (
    echo Setting local Git author email to ChardaZAR@users.noreply.github.com...
    git config user.email "ChardaZAR@users.noreply.github.com"
)

echo Staging and committing files...
git add -A
git commit -m "Deploy Cutting Room Gigs board with automated 6h job sweep"

:: Rename branch to main AFTER the commit exists
git branch -M main

git remote remove origin 2>nul
git remote add origin https://github.com/ChardaZAR/cutting-room-gigs.git

echo.
echo Pushing to https://github.com/ChardaZAR/cutting-room-gigs.git ...
git push -u origin main --force

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Push failed. Check the message above (you may need to sign in to GitHub when prompted).
    pause
    exit /b 1
)

where gh >nul 2>nul
if %errorlevel% equ 0 (
    echo Enabling GitHub Pages on main branch...
    gh api -X POST repos/ChardaZAR/cutting-room-gigs/pages -f "source[branch]=main" -f "source[path]=/" >nul 2>nul
)

echo.
echo ========================================================
echo   SUCCESS! Pushed to https://github.com/ChardaZAR/cutting-room-gigs
echo.
echo   To turn on your live site:
echo   1. Open https://github.com/ChardaZAR/cutting-room-gigs/settings/pages
echo   2. Under "Build and deployment", set Source to "Deploy from a branch"
echo   3. Choose branch "main" and "/ (root)", then click Save.
echo.
echo   Your live URL will be:
echo   https://chardazar.github.io/cutting-room-gigs/
echo ========================================================
pause
