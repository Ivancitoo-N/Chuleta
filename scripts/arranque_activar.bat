@echo off
setlocal
cd /d "%~dp0.."

echo ==================================================
echo   Chuleta - Activar arranque con Windows
echo ==================================================
echo.

".venv\Scripts\python.exe" scripts\crear_acceso_directo.py --inicio

echo.
pause
