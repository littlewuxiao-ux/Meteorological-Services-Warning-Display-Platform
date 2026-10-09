@echo off
chcp 65001 >nul
title FMSA 依赖安装
cd /d "%~dp0"

echo ========================================
echo          FMSA 依赖安装
echo ========================================
echo.
echo 将按顺序安装运行所需依赖，可重复执行。
echo 日志：%~dplogs\install.log
echo.
where python >nul 2>&1
if errorlevel 1 (
    echo 错误：未找到 python 命令，请安装 Python 3.10+ 并勾选 PATH。
    pause
    exit /b 1
)
echo 当前 Python：
python --version
echo.
set FAILED=0
if not exist "%~dplogs" mkdir "%~dplogs"
set LOG=%~dplogs\install.log
echo [%date% %time%] FMSA 依赖安装开始 > "%LOG%" 2>&1

echo [0/12] 升级 pip / setuptools / wheel ...
python -m pip install --upgrade pip setuptools wheel >> "%LOG%" 2>&1
if errorlevel 1 echo 警告：pip 升级失败，将继续。
echo [1/12] 基础工具包 ...
call :install "packaging==26.2"
call :install "six==1.17.0"
call :install "typing_extensions==4.15.0"
echo [2/12] Django（兼容3.10/3.12） ...
call :install "asgiref==3.11.1"
call :install "sqlparse==0.5.5"
call :install "Django>=4.2,<6.1"
call :install "djangorestframework==3.17.1"
echo [3/12] 时间与时区 ...
call :install "python-dateutil==2.9.0.post0"
call :install "pytz==2026.1.post1"
call :install "tzdata==2026.1"
call :install "tzlocal"
echo [4/12] 数据处理（兼容3.10） ...
call :install "numpy>=1.26,<2.3"
call :install "pandas>=2.0,<2.3"
echo [5/12] 网络请求 ...
call :install "certifi==2026.4.22"
call :install "charset-normalizer==3.4.7"
call :install "idna==3.13"
call :install "urllib3==2.6.3"
call :install "requests==2.33.1"
echo [6/12] 气象解析依赖 ...
call :install "httpcore"
call :install "httpx"
call :install "geopy"
call :install "xmltodict"
echo [7/12] 日出日落+定时 ...
call :install "suntime==1.3.2"
call :install "APScheduler==3.11.1"
echo [8/12] 图像处理 ...
call :install "Pillow==12.2.0"
echo [9/12] 服务端GUI与托盘 ...
call :install "customtkinter>=5.2.2"
call :install "pystray>=0.19.4"
echo [10/12] FMSA 托盘必需（无pywebview） ...
call :install "pywin32>=307"
echo [11/12] 可选增强（失败跳过） ...
call :install_optional "shapely"
call :install_optional "scipy"
call :install_optional "rapidfuzz"
echo [12/12] 核对关键模块 ...
python -c "import django, rest_framework, pandas, numpy, requests, PIL, suntime, apscheduler, customtkinter, pystray, httpx, geopy, xmltodict; print('关键模块导入成功')"
if errorlevel 1 (
    echo 核对失败，详见 install.log
    set FAILED=1
) else (
    echo 核对通过。
)
echo.
echo ========================================
if "%FAILED%"=="1" (
    echo 有失败项，请查看 install.log 后重试。
) else (
    echo 全部依赖安装完成，双击 启动FMSA-托盘.vbs 即可启动。
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
    set FAILED=1
) else (
    echo OK：%~1
)
goto :eof

:install_optional
echo.
echo --- 可选包 %~1 ---
python -m pip install "%~1" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo 跳过可选包：%~1，不影响主系统。
) else (
    echo OK：%~1
)
goto :eof
