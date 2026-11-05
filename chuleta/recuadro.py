"""Selector de región de pantalla mediante overlay semitransparente."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable, Optional
import platform
from PIL import Image

from .captura import habilitar_dpi_awareness

logger = logging.getLogger("chuleta.recuadro")


class SelectorRecuadro:
    """Ventana overlay fullscreen para seleccionar un recuadro con el ratón."""

    def __init__(self, root: tk.Tk):
        self._root = root
        self._overlay: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._callback: Optional[Callable[[Optional[tuple[int, int, int, int]]], None]] = None
        self._start_x = 0
        self._start_y = 0
        self._offset_x = 0
        self._offset_y = 0
        self._cur_rect: Optional[int] = None
        self._en_seleccion = False

    def iniciar_seleccion(self, on_completado: Callable[[Optional[tuple[int, int, int, int]]], None]):
        """Abre el overlay para arrastrar y seleccionar un área.
        
        Args:
            on_completado: función que recibe (x1, y1, x2, y2) o None si canceló (Esc).
        """
        self._root.after(0, lambda: self._crear_overlay(on_completado))

    def _crear_overlay(self, on_completado: Callable):
        if self._overlay:
            try:
                self._overlay.destroy()
            except Exception:
                pass

        habilitar_dpi_awareness()

        self._callback = on_completado
        self._en_seleccion = False

        self._overlay = tk.Toplevel(self._root)
        self._overlay.title("Chuleta - Seleccionar Recuadro")
        self._overlay.attributes("-alpha", 0.28)  # Ligero velo oscuro/semitransparente
        self._overlay.attributes("-topmost", True)
        self._overlay.config(cursor="crosshair")

        if platform.system() == "Windows":
            import ctypes
            u = ctypes.windll.user32
            # Escritorio virtual completo (cubre todos los monitores y escala DPI real)
            vx = u.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            vy = u.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
            vw = u.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            vh = u.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN

            if vw == 0 or vh == 0:
                vx, vy = 0, 0
                vw = u.GetSystemMetrics(0) or self._overlay.winfo_screenwidth()
                vh = u.GetSystemMetrics(1) or self._overlay.winfo_screenheight()

            self._offset_x = vx
            self._offset_y = vy
            self._overlay.overrideredirect(True)
            self._overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")
            sw, sh = vw, vh
        else:
            self._offset_x = 0
            self._offset_y = 0
            self._overlay.attributes("-fullscreen", True)
            sw = self._overlay.winfo_screenwidth()
            sh = self._overlay.winfo_screenheight()

        self._canvas = tk.Canvas(
            self._overlay,
            width=sw,
            height=sh,
            bg="black",
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<ButtonPress-3>", lambda e: self._cancelar())
        self._canvas.bind("<Escape>", lambda e: self._cancelar())
        self._overlay.bind("<ButtonPress-3>", lambda e: self._cancelar())
        self._overlay.bind("<Escape>", lambda e: self._cancelar())

        self._overlay.focus_force()

    def _on_press(self, event):
        self._start_x = event.x
        self._start_y = event.y
        self._en_seleccion = True
        if self._cur_rect:
            self._canvas.delete(self._cur_rect)
        self._cur_rect = self._canvas.create_rectangle(
            self._start_x,
            self._start_y,
            self._start_x,
            self._start_y,
            outline="#38bdf8",
            fill="#0284c7",
            width=2,
        )

    def _on_motion(self, event):
        if self._en_seleccion and self._cur_rect:
            self._canvas.coords(
                self._cur_rect,
                self._start_x,
                self._start_y,
                event.x,
                event.y,
            )

    def _on_release(self, event):
        if not self._en_seleccion:
            return
        self._en_seleccion = False

        rel_x1 = min(self._start_x, event.x)
        rel_y1 = min(self._start_y, event.y)
        rel_x2 = max(self._start_x, event.x)
        rel_y2 = max(self._start_y, event.y)

        # Coordenadas absolutas de pantalla teniendo en cuenta origen virtual
        x1 = rel_x1 + getattr(self, "_offset_x", 0)
        y1 = rel_y1 + getattr(self, "_offset_y", 0)
        x2 = rel_x2 + getattr(self, "_offset_x", 0)
        y2 = rel_y2 + getattr(self, "_offset_y", 0)

        self._cerrar()

        # Descartar clicks sin arrastre (< 10px)
        if (rel_x2 - rel_x1) < 10 or (rel_y2 - rel_y1) < 10:
            if self._callback:
                self._callback(None)
            return

        if self._callback:
            self._callback((x1, y1, x2, y2))

    def _cancelar(self):
        self._cerrar()
        if self._callback:
            self._callback(None)

    def _cerrar(self):
        if self._overlay:
            try:
                self._overlay.destroy()
            except Exception:
                pass
            self._overlay = None
            self._canvas = None
