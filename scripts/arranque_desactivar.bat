@echo off
setlocal

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo ==================================================
echo   Chuleta - Desactivar arranque con Windows
echo ==================================================
echo.

set "ELIMINADO=0"

if exist "%STARTUP%\Chuleta.lnk" (
    del "%STARTUP%\Chuleta.lnk"
    set "ELIMINADO=1"
)
if exist "%STARTUP%\Chuleta.bat" (
    del "%STARTUP%\Chuleta.bat"
    set "ELIMINADO=1"
)

if "%ELIMINADO%"=="1" (
    echo [OK] Arranque automatico desactivado correctamente.
) else (
    echo [INFO] No habia arranque automatico configurado en Inicio.
)

echo.
pause
