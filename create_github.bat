@echo off
rem ============================================================
rem  一键创建 GitHub 仓库并推送（Token 仅本次使用，不会保存）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
    echo [错误] 本机未安装 Git。请先到 https://git-scm.com/download/win 下载安装（一路下一步）。
    pause
    exit /b 1
)

echo ============================================================
echo  一键创建 GitHub 仓库并推送
echo  （Token 获取：github.com - Settings - Developer settings -
echo   Personal access tokens - Tokens classic - 勾选 repo 权限）
echo ============================================================
set /p GITHUB_USER=① 输入 GitHub 用户名:
if "%GITHUB_USER%"=="" ( echo 未输入用户名 & pause & exit /b 1 )
set /p GITHUB_TOKEN=② 粘贴 Token（ghp_ 开头，直接右键粘贴）:
if "%GITHUB_TOKEN%"=="" ( echo 未输入 Token & pause & exit /b 1 )
set /p REPO_NAME=③ 仓库名（直接回车用默认 quant-app）:
if "%REPO_NAME%"=="" set REPO_NAME=quant-app

echo.
echo [1/3] 创建仓库 %REPO_NAME% …
curl -s -X POST https://api.github.com/user/repos -H "Authorization: token %GITHUB_TOKEN%" -H "Accept: application/vnd.github+json" -d "{\"name\":\"%REPO_NAME%\",\"private\":false,\"description\":\"Quant Studio - multi-market quant backtesting web app\"}" -o nul
echo        （若提示已存在则直接复用）

echo [2/3] 推送代码（首次约 10 秒）…
git remote remove origin 2>nul
git remote add origin https://%GITHUB_USER%:%GITHUB_TOKEN%@github.com/%GITHUB_USER%/%REPO_NAME%.git
git branch -M main
git push -u origin main
set PUSH_OK=%errorlevel%

echo [3/3] 清理：不把 Token 留在仓库配置里…
git remote set-url origin https://github.com/%GITHUB_USER%/%REPO_NAME%.git

echo.
if %PUSH_OK%==0 (
    echo 🎉 完成！仓库地址：https://github.com/%GITHUB_USER%/%REPO_NAME%
    echo    下一步：去 koyeb.com 用它部署（参考 README 方案四）
) else (
    echo [失败] 请检查：① 用户名是否正确 ② Token 是否勾选了 repo 权限 ③ 网络
)
pause
