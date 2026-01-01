@echo off
chcp 65001 >nul

echo ==============================================
echo        通过 PowerShell 运行 IPTV 脚本
echo ==============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "cd /d '%~dp0'; python iptv_m3u_get.py"

echo.
echo 运行完成，按任意键退出...
pause >nul
