@echo off
setlocal

echo ==================================================
echo   Chuleta - Detener aplicacion
echo ==================================================
echo.

powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*chuleta*' -and $_.ProcessId -ne $PID }; if ($procs) { $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('Detenido proceso con PID: ' + $_.ProcessId) }; Write-Output '[OK] Chuleta se ha detenido correctamente.'; } else { Write-Output '[INFO] Chuleta no estaba en ejecucion.'; }"

echo.
ping -n 3 127.0.0.1 >nul
