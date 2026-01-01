@echo off
chcp 65001 > nul
echo ==============================================
echo          通过PowerShell运行IPTV脚本
echo ==============================================
echo.

:: 调用PowerShell执行Python脚本（关键命令）
:: 说明：
:: 1. -ExecutionPolicy Bypass：临时绕过PowerShell的执行策略（无需修改系统全局策略）
:: 2. -Command：指定要执行的PowerShell命令
:: 3. & python "你的脚本文件名.py"：在PowerShell中调用python命令运行脚本（& 用于执行外部命令）
:: 4. 请将「你的脚本文件名.py」替换为实际的Python脚本名称（如 extract_m3u.py）
powershell -ExecutionPolicy Bypass -Command "& python 'iptv_m3u_get.py'; pause"

:: 批处理窗口额外暂停（可选）
pause > nul