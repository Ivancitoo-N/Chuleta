"""Icono de bandeja del sistema con menú."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw

from .config import DIR_DOCUMENTOS, ARCHIVO_CONFIG

logger = logging.getLogger("chuleta.bandeja")

SISTEMA = platform.system()


def _crear_icono_imagen(tamaño: int = 64) -> Image.Image:
    """Crea un icono programáticamente (un libro estilizado)."""
    img = Image.new("RGBA", (tamaño, tamaño), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo redondeado
    margen = 4
    draw.rounded_rectangle(
        [margen, margen, tamaño - margen, tamaño - margen],
        radius=10,
        fill=(99, 102, 241),  # Índigo
    )

    # Letras "Ch" en blanco
    cx, cy = tamaño // 2, tamaño // 2
    # Líneas simulando un libro abierto
    draw.line(
        [(cx, margen + 10), (cx, tamaño - margen - 10)],
        fill="white", width=2,
    )
    # Páginas izquierda
    draw.arc(
        [margen + 6, cy - 12, cx, cy + 12],
        start=90, end=270,
        fill="white", width=2,
    )
    # Páginas derecha
    draw.arc(
        [cx, cy - 12, tamaño - margen - 6, cy + 12],
        start=-90, end=90,
        fill="white", width=2,
    )
    # Líneas horizontales (texto)
    for y_off in [-6, 0, 6]:
        draw.line(
            [(margen + 14, cy + y_off), (cx - 4, cy + y_off)],
            fill=(200, 200, 255), width=1,
        )
        draw.line(
            [(cx + 4, cy + y_off), (tamaño - margen - 14, cy + y_off)],
            fill=(200, 200, 255), width=1,
        )

    return img


def _abrir_carpeta(ruta: Path):
    """Abre una carpeta en el explorador de archivos."""
    ruta.mkdir(parents=True, exist_ok=True)
    try:
        if SISTEMA == "Windows":
            os.startfile(str(ruta))
        elif SISTEMA == "Darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta)])
    except Exception as e:
        logger.error(f"Error abriendo carpeta: {e}")


def _abrir_archivo(ruta: Path):
    """Abre un archivo con la aplicación predeterminada."""
    try:
        if SISTEMA == "Windows":
            os.startfile(str(ruta))
        elif SISTEMA == "Darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta)])
    except Exception as e:
        logger.error(f"Error abriendo archivo: {e}")


class Bandeja:
    """Icono en la bandeja del sistema."""

    def __init__(
        self,
        on_reindexar: Callable,
        on_salir: Callable,
        on_ver_uso: Optional[Callable] = None,
    ):
        self._on_reindexar = on_reindexar
        self._on_salir = on_salir
        self._on_ver_uso = on_ver_uso
        self._icon = None

    def _ver_uso(self):
        if self._on_ver_uso:
            self._on_ver_uso()

    def iniciar(self):
        """Inicia el icono de la bandeja en un hilo separado."""
        import pystray

        imagen = _crear_icono_imagen()

        menu = pystray.Menu(
            pystray.MenuItem(
                "Ver uso de hoy",
                lambda: self._ver_uso(),
            ),
            pystray.MenuItem(
                "Reindexar documentos",
                lambda: self._on_reindexar(),
            ),
            pystray.MenuItem(
                "Abrir carpeta de documentos",
                lambda: _abrir_carpeta(DIR_DOCUMENTOS),
            ),
            pystray.MenuItem(
                "Abrir config.toml",
                lambda: _abrir_archivo(ARCHIVO_CONFIG),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Salir",
                lambda: self._salir(),
            ),
        )

        self._icon = pystray.Icon(
            "Chuleta",
            imagen,
            "Chuleta – Herramienta de estudio",
            menu,
        )

        # Ejecutar en hilo separado para no bloquear
        hilo = threading.Thread(target=self._icon.run, daemon=True)
        hilo.start()
        logger.info("Bandeja del sistema iniciada")

    def _salir(self):
        """Detiene el icono y llama al callback de salida."""
        if self._icon:
            self._icon.stop()
        self._on_salir()

    def detener(self):
        """Detiene el icono de la bandeja."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
