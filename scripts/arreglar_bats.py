"""Restaura todos los scripts BAT con codificación CRLF correcta."""

from pathlib import Path

iniciar = """@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo   Chuleta - Asistente de estudio
echo ==================================================
echo.

if not exist ".venv\\Scripts\\pythonw.exe" (
    echo [ERROR] No se encuentra el entorno virtual en .venv.
    pause
    exit /b 1
)

powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*chuleta*' -and $_.ProcessId -ne $PID }; if ($p) { exit 42 } else { exit 0 }"
if %ERRORLEVEL% equ 42 goto ya_ejecutando

start "" "%~dp0.venv\\Scripts\\pythonw.exe" -m chuleta

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
"""

detener = """@echo off
setlocal

echo ==================================================
echo   Chuleta - Detener aplicacion
echo ==================================================
echo.

powershell -NoProfile -Command "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*chuleta*' -and $_.ProcessId -ne $PID }; if ($procs) { $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('Detenido proceso con PID: ' + $_.ProcessId) }; Write-Output '[OK] Chuleta se ha detenido correctamente.'; } else { Write-Output '[INFO] Chuleta no estaba en ejecucion.'; }"

echo.
ping -n 3 127.0.0.1 >nul
"""

crear_lnk = """@echo off
setlocal
cd /d "%~dp0.."

echo ==================================================
echo   Chuleta - Crear acceso directo en el Escritorio
echo ==================================================
echo.

".venv\\Scripts\\python.exe" scripts\\crear_acceso_directo.py

echo.
pause
"""

arranque_act = """@echo off
setlocal
cd /d "%~dp0.."

echo ==================================================
echo   Chuleta - Activar arranque con Windows
echo ==================================================
echo.

".venv\\Scripts\\python.exe" scripts\\crear_acceso_directo.py --inicio

echo.
pause
"""

arranque_des = """@echo off
setlocal

set "STARTUP=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"

echo ==================================================
echo   Chuleta - Desactivar arranque con Windows
echo ==================================================
echo.

set "ELIMINADO=0"

if exist "%STARTUP%\\Chuleta.lnk" (
    del "%STARTUP%\\Chuleta.lnk"
    set "ELIMINADO=1"
)
if exist "%STARTUP%\\Chuleta.bat" (
    del "%STARTUP%\\Chuleta.bat"
    set "ELIMINADO=1"
)

if "%ELIMINADO%"=="1" (
    echo [OK] Arranque automatico desactivado correctamente.
) else (
    echo [INFO] No habia arranque automatico configurado en Inicio.
)

echo.
pause
"""

instalar = """@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo   Chuleta - Instalador automatico
echo ==================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] No se ha encontrado Python en el sistema.
    echo Por favor instala Python 3.10 o superior marcando la casilla
    echo "Add Python to PATH" durante la instalacion:
    echo https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

if not exist ".venv\\Scripts\\python.exe" (
    echo [1/4] Creando entorno virtual (.venv)...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Entorno virtual existente detectado.
)

echo [2/4] Instalando dependencias de requirements.txt...
".venv\\Scripts\\python.exe" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Fallo al instalar las dependencias.
    pause
    exit /b 1
)

echo [3/4] Configurando archivo de claves (.env)...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo      Archivo .env creado a partir de .env.example.
) else (
    echo      Archivo .env ya existente (no se sobreescribe).
)

echo [4/4] Creando acceso directo en el Escritorio...
".venv\\Scripts\\python.exe" "scripts\\crear_acceso_directo.py"

echo.
echo ==================================================
echo   [OK] Instalacion completada con exito!
echo ==================================================
echo.
echo Pasos siguientes:
echo 1. Abre el archivo .env y pon tu clave gratuita de Gemini:
echo    GEMINI_API_KEY=tu_clave_aqui
echo    (Consiguela gratis en https://aistudio.google.com/apikey)
echo.
echo 2. Pon tus apuntes (PDF, MD, TXT) en la carpeta "documentos".
echo.
echo 3. Inicia Chuleta haciendo doble clic en "iniciar.bat"
echo    o desde el acceso directo de tu Escritorio.
echo.
pause
"""

def write_crlf(filename: str, content: str):
    p = Path(filename)
    b = content.strip().replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8") + b"\r\n"
    with open(p, "wb") as f:
        f.write(b)
    print(f"[OK] {filename} escrito: {len(b)} bytes")

def main():
    write_crlf("instalar.bat", instalar)
    write_crlf("iniciar.bat", iniciar)
    write_crlf("detener.bat", detener)
    write_crlf("scripts/crear_acceso_directo.bat", crear_lnk)
    write_crlf("scripts/arranque_activar.bat", arranque_act)
    write_crlf("scripts/arranque_desactivar.bat", arranque_des)

if __name__ == "__main__":
    main()
