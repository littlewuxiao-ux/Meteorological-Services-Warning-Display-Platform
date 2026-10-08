@echo off
chcp 65001 >nul
title MTWS 依赖安装
cd /d "%~dp0"

echo ========================================
echo          MTWS 依赖安装
echo ========================================
echo.
echo 将使用当前 Python 环境按顺序安装运行所需依赖。
echo 已安装的包会按指定版本补齐，可重复执行。
echo 日志：%~dp0install.log
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo 错误：未找到 python 命令。
    echo 请先安装 Python 3.10+ 并勾选 "Add python.exe to PATH"。
    pause
    exit /b 1
)
echo 当前 Python：
python --version
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo 错误：需要 Python 3.10 及以上版本。
    pause
    exit /b 1
)
echo.

set FAILED=0
set LOG=%~dp0install.log
echo [%date% %time%] MTWS 依赖安装开始 > "%LOG%" 2>&1

echo [0/14] 升级 pip / setuptools / wheel ...
python -m pip install --upgrade pip setuptools wheel >> "%LOG%" 2>&1
if errorlevel 1 echo 警告：pip 升级失败，将继续尝试安装依赖。

REM 基础工具 -> Web 框架 -> 时间 -> 数据 -> 网络 -> 气象解析 -> 定时 -> 图像 -> GUI/托盘 -> App单窗口 -> 可选增强
echo [1/14] 安装基础工具包 ...
call :install "packaging==26.2"
call :install "six==1.17.0"
call :install "typing_extensions==4.15.0"

echo [2/14] 安装 Django ...
call :install "asgiref==3.11.1"
call :install "sqlparse==0.5.5"
call :install "Django>=4.2,<6.1"
call :install "djangorestframework==3.17.1"

echo [3/14] 安装时间与时区相关包 ...
call :install "python-dateutil==2.9.0.post0"
call :install "pytz==2026.1.post1"
call :install "tzdata==2026.1"
call :install "tzlocal"

echo [4/14] 安装数据处理包 ...
call :install "numpy>=1.26,<2.3"
call :install "pandas>=2.0,<2.3"

echo [5/14] 安装网络请求包 ...
call :install "certifi==2026.4.22"
call :install "charset-normalizer==3.4.7"
call :install "idna==3.13"
call :install "urllib3==2.6.3"
call :install "requests==2.33.1"

echo [6/14] 安装气象解析依赖 ^(avwx_custom^) ...
call :install "httpcore"
call :install "httpx"
call :install "geopy"
call :install "xmltodict"

echo [7/14] 安装日出日落计算包 ...
call :install "suntime==1.3.2"

echo [8/14] 安装定时任务包 ...
call :install "APScheduler==3.11.1"

echo [9/14] 安装图像处理包 ...
call :install "Pillow==12.2.0"

echo [10/14] 安装服务端 GUI 与托盘包 ...
call :install "customtkinter>=5.2.2"
call :install "pystray>=0.19.4"

echo [11/14] 安装 App 单窗口包 ^(app_launcher.py 必需^) ...
call :install "pywebview>=5.1"

echo [12/14] 安装 Windows 增强包 ...
call :install "pywin32>=307"

echo [13/14] 安装可选增强包 ^(地图生成 / 机场搜索，缺失不影响主系统启动^) ...
call :install_optional "shapely"
call :install_optional "scipy"
call :install_optional "rapidfuzz"

echo [14/14] 正在核对关键模块 ...
python -c "import django, rest_framework, pandas, numpy, requests, PIL, suntime, apscheduler, customtkinter, pystray, webview, httpx, geopy, xmltodict; print('关键模块导入成功')"
if errorlevel 1 (
    echo 核对失败：部分关键模块无法导入，详见 install.log
    set FAILED=1
) else (
    echo 核对通过。
)
python -c "import webview; print('App 单窗口依赖 OK')" >> "%LOG%" 2>&1

echo.
echo ========================================
if "%FAILED%"=="1" (
    echo 安装过程中有失败项，请查看 install.log 后重试。
) else (
    echo 全部依赖已按顺序安装完成。
)
echo ========================================
echo.
pause
exit /b %FAILED%

:install
echo.
echo --- 正在安装 %~1 ---
python -m pip install "%~1" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo *** 安装失败：%~1，详见 install.log ***
    echo see install.log
    set FAILED=1
) else (
    echo OK：%~1
)
goto :eof

:install_optional
echo.
echo --- 正在安装可选包 %~1 ---
python -m pip install "%~1" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo 跳过可选包：%~1 安装失败，不影响主系统。
) else (
    echo OK：%~1
)
goto :eof
