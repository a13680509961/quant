@echo off
rem 取消开机自启
chcp 65001 >nul
schtasks /delete /tn "QuantStudio" /f
echo 已取消开机自启。
pause
