@echo off
chcp 65001 >nul
title FMSA系统启动器

echo ========================================
echo          FMSA系统启动器
echo ========================================
echo.

echo 正在启动FMSA系统...
echo.

REM 进入Django项目目录
cd /d "%~dp0fmsa_django"

REM 检查是否在正确目录
if not exist "manage.py" (
    echo 错误：找不到manage.py文件
    echo 请确保脚本位于项目根目录
    pause
    exit /b 1
)

echo 📋 快速检查Django配置...
python manage.py check
if %errorlevel% neq 0 (
    echo ⚠️  Django配置检查发现问题，但继续启动...
    echo.
)

echo 🚀 启动Django开发服务器...
echo.
echo ========================================
echo 🌐 系统访问地址：
echo    http://localhost:8000/current/
echo    http://127.0.0.1:8000/current/
echo ========================================
echo.
echo 💡 使用说明：
echo    - 在浏览器中打开上述地址访问系统
echo    - 按 Ctrl+C 停止服务器
echo    - 关闭此窗口也会停止服务器
echo.
echo ========================================

REM 启动Django服务器
python manage.py runserver 127.0.0.1:8000

echo.
echo 服务器已停止运行
pause


