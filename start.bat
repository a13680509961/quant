@echo off
rem ============================================================
rem  量化分析工作台 · 一键启动
rem  自动寻找带 numpy/pandas 的 Python（优先系统 python，其次 DSH 内置）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "PYCMD="
python -c "import numpy,pandas" >nul 2>nul && set "PYCMD=python"
if not defined PYCMD if exist "%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" set "PYCMD=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"

if not defined PYCMD (
    echo.
    echo [错误] 未找到可用的 Python 环境（需要 numpy 和 pandas）。
    echo        方案1：pip install numpy pandas 后重试；
    echo        方案2：参考 README.md 手动指定 Python。
    echo.
    pause
    exit /b 1
)

echo 正在启动量化分析工作台（浏览器将自动打开）...
echo 停止服务请按 Ctrl+C
echo.
"%PYCMD%" app.py
pause
