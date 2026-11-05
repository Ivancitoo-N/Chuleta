@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo   Chuleta - Asistente de estudio
echo ==================================================
echo.

if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERROR] No se encuentra el entorno virtual en .venv.
    pause
    exit /b 1
)

powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*chuleta*' -and $_.ProcessId -ne $PID }; if ($p) { exit 42 } else { exit 0 }"
if %ERRORLEVEL% equ 42 goto ya_ejecutando

start "" "%~dp0.venv\Scripts\pythonw.exe" -m chuleta

echo [OK] Chuleta iniciada en segundo plano con exito.
echo.
echo Atajos disponibles:
echo   - Ctrl+Alt+Q : Responder pregunta seleccionada
echo   - Ctrl+Alt+E : Repasar termino o concepto seleccionado
echo   - Ctrl+Alt+S : Capturar recuadro de pantalla (esquemas/dibujos/canvas)
echo.
echo Icono disponible en la bandeja del sistema (junto al reloj).
echo Para cerrar la aplicacion, usa el icono de la bandeja o ejecuta detener.bat.
echo.
ping -n 3 127.0.0.1 >nul
exit /b 0

:ya_ejecutando
echo [INFO] Chuleta ya esta en ejecucion en segundo plano.
echo Puedes ver su icono en la bandeja del sistema, junto al reloj.
echo.
echo Atajos activos:
echo   - Ctrl+Alt+Q : Responder a lo seleccionado
echo   - Ctrl+Alt+E : Repasar concepto
echo   - Ctrl+Alt+S : Capturar recuadro de pantalla (esquemas/dibujos/canvas)
echo.
ping -n 3 127.0.0.1 >nul
exit /b 0
