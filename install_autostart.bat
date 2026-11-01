@echo off
rem ============================================================
rem  一键设置：开机自动上线（固定子域名，免费）
rem  设置后每次开机自动启动应用 + 公网隧道，地址固定
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set /p NAME=请输入固定子域名（字母数字，如 quantstudio，直接回车用默认）:
if "%NAME%"=="" set NAME=quantstudio

set "PYCMD="
python -c "import numpy,pandas" >nul 2>nul && set "PYCMD=python"
if not defined PYCMD if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYCMD=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
if not defined PYCMD (
    echo [错误] 未找到可用 Python（需 numpy/pandas）。请参考 README.md
    pause
    exit /b 1
)

schtasks /create /tn "QuantStudio" /tr "\"%PYCMD%\" \"%~dp0serve_public.py\" --subdomain %NAME%" /sc onstart /ru SYSTEM /rl highest /f

echo.
echo ============================================================
echo  ✅ 开机自启已设置：每次开机自动上线
echo     公网地址：https://%NAME%.tunnelmole.net（固定不变）
echo     若该名字被占用，会自动改用随机地址（见 public_url.txt）
echo  （取消自启：双击 uninstall_autostart.bat）
echo ============================================================
echo.
echo 现在立即启动一次上线（关闭本窗口即断开）：
"%PYCMD%" "%~dp0serve_public.py" --subdomain %NAME%
pause
