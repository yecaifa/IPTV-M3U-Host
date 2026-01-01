@echo off
chcp 65001 > nul
echo ==============================================
echo          PowerShell运行
echo ==============================================
echo.
powershell -ExecutionPolicy Bypass -Command "& python 'iptv_m3u_get.py'; pause"

pause > nul