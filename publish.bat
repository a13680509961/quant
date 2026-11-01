@echo off
rem ============================================================
rem  量化应用 · 一键发布到公网
rem  （Cloudflare 隧道优先，网络受限时自动切换 localtunnel）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "PYCMD="
python -c "import numpy,pandas" >nul 2>nul && set "PYCMD=python"
if not defined PYCMD if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYCMD=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if not defined PYCMD (
    echo [错误] 未找到可用 Python（需 numpy/pandas）。请参考 README.md
    pause
    exit /b 1
)

"%PYCMD%" publish.py
pause
