@echo off
setlocal
cd /d "%~dp0.."

echo ==================================================
echo   Chuleta - Crear acceso directo en el Escritorio
echo ==================================================
echo.

".venv\Scripts\python.exe" scripts\crear_acceso_directo.py

echo.
pause
