"""Crea el acceso directo de Chuleta en el Escritorio o en Inicio."""

import os
import sys
import subprocess
from pathlib import Path

def crear_acceso(destino: str = "escritorio"):
    raiz = Path(__file__).resolve().parent.parent

    if destino == "inicio":
        carpeta = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    else:
        carpeta = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
        if not carpeta.exists():
            carpeta = Path.home() / "Desktop"

    acceso_lnk = carpeta / "Chuleta.lnk"
    pythonw = raiz / ".venv" / "Scripts" / "pythonw.exe"
    icono = raiz / "chuleta.ico"

    if not pythonw.exists():
        print(f"[ERROR] No se encuentra {pythonw}")
        return False

    ps_cmd = f"""
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut('{acceso_lnk}')
    $s.TargetPath = '{pythonw}'
    $s.Arguments = '-m chuleta'
    $s.WorkingDirectory = '{raiz}'
    $s.Description = 'Chuleta - Asistente de estudio en segundo plano'
    if (Test-Path '{icono}') {{
        $s.IconLocation = '{icono},0'
    }}
    $s.Save()
    """

    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
    )

    if res.returncode == 0 and acceso_lnk.exists():
        print(f"[OK] Acceso directo creado en: {acceso_lnk}")
        return True
    else:
        print(f"[ERROR] Fallo al crear acceso directo: {res.stderr}")
        return False

if __name__ == "__main__":
    destino = "inicio" if "--inicio" in sys.argv else "escritorio"
    crear_acceso(destino)
