"""Cuadro de respuesta: overlay tkinter sin bordes, transparente, siempre encima."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import Optional

from .config import Config

logger = logging.getLogger("chuleta.cuadro")


class CuadroRespuesta:
    """Cuadro flotante que muestra la respuesta junto al cursor."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._root: Optional[tk.Tk] = None
        self._ventana: Optional[tk.Toplevel] = None
        self._timer_id: Optional[str] = None
        self._lock = threading.Lock()
        self._inicializado = False

    def inicializar(self, root: tk.Tk):
        """Inicializa con la ventana root de tkinter."""
        self._root = root
        self._inicializado = True

    def _pos_cursor(self) -> tuple[int, int]:
        """Obtiene la posición actual del cursor."""
        try:
            # Usar el método de tkinter
            x = self._root.winfo_pointerx()
            y = self._root.winfo_pointery()
            return x, y
        except Exception:
            return 100, 100

    def _ajustar_posicion(
        self, x: int, y: int, ancho: int, alto: int
    ) -> tuple[int, int]:
        """Ajusta la posición para que no se salga de la pantalla."""
        try:
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
        except Exception:
            screen_w, screen_h = 1920, 1080

        # Offset: 15px abajo y a la derecha del cursor
        x += 15
        y += 15

        # No salirse por la derecha
        if x + ancho > screen_w:
            x = screen_w - ancho - 10

        # No salirse por abajo
        if y + alto > screen_h:
            y = y - alto - 30  # Mostrar arriba del cursor

        # No salirse por la izquierda o arriba
        x = max(5, x)
        y = max(5, y)

        return x, y

    def mostrar(
        self,
        texto: str,
        fuente: str = "",
        duracion_seg: Optional[float] = None,
    ):
        """Muestra el cuadro con el texto dado.

        Si ya hay uno visible, lo reemplaza.
        """
        if not self._inicializado or not self._root:
            return

        # Programar en el hilo de tkinter
        self._root.after(0, lambda: self._mostrar_impl(texto, fuente, duracion_seg))

    def _mostrar_impl(
        self,
        texto: str,
        fuente: str = "",
        duracion_seg: Optional[float] = None,
    ):
        """Implementación interna (debe ejecutarse en el hilo de tkinter)."""
        # Cerrar cuadro anterior si existe
        self._cerrar_impl()

        cfg_cuadro = self.cfg.cuadro

        # Calcular duración
        if duracion_seg is None:
            palabras = len(texto.split())
            duracion_seg = max(
                cfg_cuadro.segundos_min,
                min(
                    palabras * cfg_cuadro.segundos_por_palabra,
                    cfg_cuadro.segundos_max,
                ),
            )

        # Crear ventana toplevel
        ventana = tk.Toplevel(self._root)
        ventana.overrideredirect(True)  # Sin bordes
        ventana.attributes("-topmost", True)  # Siempre encima
        ventana.attributes("-alpha", cfg_cuadro.opacidad)

        # No aparecer en la barra de tareas (Windows)
        ventana.attributes("-toolwindow", True)

        # Tema oscuro
        bg_color = "#1e1e2e"
        fg_color = "#cdd6f4"
        fg_fuente = "#6c7086"

        ventana.configure(bg=bg_color)

        # Frame contenedor con padding
        frame = tk.Frame(ventana, bg=bg_color, padx=12, pady=8)
        frame.pack(fill=tk.BOTH, expand=True)

        # Texto principal
        label_texto = tk.Label(
            frame,
            text=texto,
            bg=bg_color,
            fg=fg_color,
            font=("Segoe UI", 11),
            wraplength=cfg_cuadro.ancho - 30,
            justify=tk.LEFT,
            anchor=tk.W,
        )
        label_texto.pack(fill=tk.X, pady=(0, 2))

        # Fuente (si la hay)
        if fuente:
            label_fuente = tk.Label(
                frame,
                text=fuente,
                bg=bg_color,
                fg=fg_fuente,
                font=("Segoe UI", 9),
                wraplength=cfg_cuadro.ancho - 30,
                justify=tk.LEFT,
                anchor=tk.W,
            )
            label_fuente.pack(fill=tk.X)

        # Actualizar para calcular tamaño
        ventana.update_idletasks()

        ancho = max(ventana.winfo_reqwidth(), 150)
        alto = ventana.winfo_reqheight()

        # Posición junto al cursor
        cx, cy = self._pos_cursor()
        x, y = self._ajustar_posicion(cx, cy, ancho, alto)

        ventana.geometry(f"{ancho}x{alto}+{x}+{y}")

        # Evitar que la ventana emergente robe el foco en Windows
        import platform
        if platform.system() == "Windows":
            try:
                import ctypes
                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                hwnd = ventana.winfo_id()
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
            except Exception:
                pass

        # Clic para cerrar
        for widget in [ventana, frame, label_texto]:
            widget.bind("<Button-1>", lambda e: self._cerrar_impl())

        self._ventana = ventana

        # Temporizador para cerrar
        ms = int(duracion_seg * 1000)
        self._timer_id = self._root.after(ms, self._cerrar_impl)

    def mostrar_espera(self):
        """Muestra '…' mientras se procesa."""
        self.mostrar("…", duracion_seg=30)

    def cerrar(self):
        """Cierra el cuadro (thread-safe)."""
        if self._root:
            self._root.after(0, self._cerrar_impl)

    def _cerrar_impl(self):
        """Cierra el cuadro (hilo de tkinter)."""
        if self._timer_id and self._root:
            try:
                self._root.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None

        if self._ventana:
            try:
                self._ventana.destroy()
            except Exception:
                pass
            self._ventana = None
