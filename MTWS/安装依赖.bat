@echo off
chcp 65001 >nul
title FMSA ������װ
cd /d "%~dp0"

echo ========================================
echo          FMSA ������װ
echo ========================================
echo.
echo ����˳��װ�����������������ظ�ִ�С�
echo ��־��%~dplogs\install.log
echo.
where python >nul 2>&1
if errorlevel 1 (
    echo ����δ�ҵ� python ����밲װ Python 3.10+ ����ѡ PATH��
    pause
    exit /b 1
)
echo ��ǰ Python��
python --version
echo.
set FAILED=0
if not exist "%~dplogs" mkdir "%~dplogs"
set LOG=%~dplogs\install.log
echo [%date% %time%] FMSA ������װ��ʼ > "%LOG%" 2>&1

echo [0/12] ���� pip / setuptools / wheel ...
python -m pip install --upgrade pip setuptools wheel >> "%LOG%" 2>&1
if errorlevel 1 echo ���棺pip ����ʧ�ܣ���������
echo [1/12] �������߰� ...
call :install "packaging==26.2"
call :install "six==1.17.0"
call :install "typing_extensions==4.15.0"
echo [2/12] Django������3.10/3.12�� ...
call :install "asgiref==3.11.1"
call :install "sqlparse==0.5.5"
call :install "Django>=4.2,<6.1"
call :install "djangorestframework==3.17.1"
echo [3/12] ʱ����ʱ�� ...
call :install "python-dateutil==2.9.0.post0"
call :install "pytz==2026.1.post1"
call :install "tzdata==2026.1"
call :install "tzlocal"
echo [4/12] ���ݴ���������3.10�� ...
call :install "numpy>=1.26,<2.3"
call :install "pandas>=2.0,<2.3"
echo [5/12] �������� ...
call :install "certifi==2026.4.22"
call :install "charset-normalizer==3.4.7"
call :install "idna==3.13"
call :install "urllib3==2.6.3"
call :install "requests==2.33.1"
echo [6/12] ����������� ...
call :install "httpcore"
call :install "httpx"
call :install "geopy"
call :install "xmltodict"
echo [7/12] �ճ�����+��ʱ ...
call :install "suntime==1.3.2"
call :install "APScheduler==3.11.1"
echo [8/12] ͼ���� ...
call :install "Pillow==12.2.0"
echo [9/12] �����GUI������ ...
call :install "customtkinter>=5.2.2"
call :install "pystray>=0.19.4"
echo [10/12] FMSA ���̱��裨��pywebview�� ...
call :install "pywin32>=307"
echo [11/12] ��ѡ��ǿ��ʧ�������� ...
call :install_optional "shapely"
call :install_optional "scipy"
call :install_optional "rapidfuzz"
echo [12/12] �˶Թؼ�ģ�� ...
python -c "import django, rest_framework, pandas, numpy, requests, PIL, suntime, apscheduler, customtkinter, pystray, httpx, geopy, xmltodict; print('�ؼ�ģ�鵼��ɹ�')"
if errorlevel 1 (
    echo �˶�ʧ�ܣ���� install.log
    set FAILED=1
) else (
    echo �˶�ͨ����
)
echo.
echo ========================================
if "%FAILED%"=="1" (
    echo ��ʧ�����鿴 install.log �����ԡ�
) else (
    echo ȫ��������װ��ɣ�˫�� ����FMSA-����.vbs ����������
)
echo ========================================
echo.
pause
exit /b %FAILED%

:install
echo.
echo --- ���ڰ�װ %~1 ---
python -m pip install "%~1" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo *** ��װʧ�ܣ�%~1����� install.log ***
    set FAILED=1
) else (
    echo OK��%~1
)
goto :eof

:install_optional
echo.
echo --- ��ѡ�� %~1 ---
python -m pip install "%~1" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo ������ѡ����%~1����Ӱ����ϵͳ��
) else (
    echo OK��%~1
)
goto :eof
