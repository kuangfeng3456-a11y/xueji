@echo off
chcp 65001 >nul
cd /d %~dp0
echo [tikuAdapter] 启动题库适配器，端口 8060 ...
echo [tikuAdapter] 网页版 http://localhost:8060  账号 admin / 123456
tikuAdapter.exe
pause
