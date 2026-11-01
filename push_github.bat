@echo off
rem ============================================================
rem  一键推送到 GitHub（需先在 github.com 创建好空仓库并登录过）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set /p REPO=请输入你的仓库地址（如 https://github.com/你的用户名/quant-app.git）:
if "%REPO%"=="" (
    echo 未输入仓库地址，请在 github.com 先创建一个新仓库后重试
    pause
    exit /b 1
)

git remote remove origin 2>nul
git remote add origin %REPO%
git branch -M main
git push -u origin main

if %errorlevel%==0 (
    echo.
    echo 🎉 推送成功！仓库地址：%REPO%
) else (
    echo.
    echo [提示] 推送失败：首次使用需在浏览器完成 GitHub 登录授权，
    echo        或使用 Personal Access Token 作为密码。
)
pause
