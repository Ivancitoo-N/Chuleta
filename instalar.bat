@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo   Chuleta - Instalador automatico
echo ==================================================
echo.

:: 1. Verificar si python esta instalado
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

:: 2. Crear entorno virtual si no existe
if not exist ".venv\Scripts\python.exe" (
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

:: 3. Instalar o actualizar dependencias
echo [2/4] Instalando dependencias de requirements.txt...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Fallo al instalar las dependencias.
    pause
    exit /b 1
)

:: 4. Copiar .env.example a .env si no existe
echo [3/4] Configurando archivo de claves (.env)...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo      Archivo .env creado a partir de .env.example.
) else (
    echo      Archivo .env ya existente (no se sobreescribe).
)

:: 5. Crear acceso directo en el Escritorio
echo [4/4] Creando acceso directo en el Escritorio...
".venv\Scripts\python.exe" "scripts\crear_acceso_directo.py"

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
