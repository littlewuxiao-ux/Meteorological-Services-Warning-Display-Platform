@echo off
chcp 65001 >nul
title MTWS App
cd /d "%~dp0"
start "" /min pythonw.exe app_launcher.py
