@echo off
setlocal EnableExtensions
cd /d "%~dp0"
REM ASCII only. Chinese in this file is parsed incorrectly by cmd.exe.
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: python was not found.
    echo Install Python 3.12+ and enable "Add python.exe to PATH".
    pause
    exit /b 1
)
python "%~dp0install_deps.py"
set ERR=%ERRORLEVEL%
echo.
pause
exit /b %ERR%
