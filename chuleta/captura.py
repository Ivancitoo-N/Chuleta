"""Captura de selección y atajos globales."""

from __future__ import annotations

import logging
import platform
import time
import threading
from typing import Callable, Optional

import pyperclip

logger = logging.getLogger("chuleta.captura")

SISTEMA = platform.system()


def habilitar_dpi_awareness():
    """Habilita DPI awareness en Windows para que Tkinter y capturas usen resolución física real."""
    if SISTEMA == "Windows":
        try:
            import ctypes
            # Per-Monitor V2 (Windows 10 1703+)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                # Per-Monitor V1 (Windows 8.1+)
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    # System DPI Aware (Windows Vista+)
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass


def capturar_pantalla_region(region: tuple[int, int, int, int]) -> Optional["Image.Image"]:
    """Captura una región específica de la pantalla (x1, y1, x2, y2)."""
    from PIL import Image
    x1, y1, x2, y2 = region
    ancho = max(1, x2 - x1)
    alto = max(1, y2 - y1)

    if SISTEMA == "Windows":
        import ctypes
        from ctypes import wintypes

        habilitar_dpi_awareness()

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        # Multiplicador DPI si corresponde
        screen_w_tk = user32.GetSystemMetrics(0)
        screen_h_tk = user32.GetSystemMetrics(1)

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, ancho, alto)
        gdi32.SelectObject(hdc_mem, hbmp)

        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(hdc_mem, 0, 0, ancho, alto, hdc_screen, x1, y1, SRCCOPY)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = ancho
        bmi.biHeight = -alto  # top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = ctypes.create_string_buffer(ancho * alto * 4)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, alto, buf, ctypes.byref(bmi), 0)

        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        img = Image.frombuffer("RGBA", (ancho, alto), buf, "raw", "BGRA", 0, 1)
        return img.convert("RGB")
    else:
        from PIL import ImageGrab
        try:
            return ImageGrab.grab(bbox=(x1, y1, x2, y2))
        except Exception as e:
            logger.error(f"Error capturando región con ImageGrab: {e}")
            return None


def _simular_copiar():
    """Simula Ctrl+C (o Cmd+C en macOS) para copiar la selección de forma limpia."""
    if SISTEMA == "Windows":
        import ctypes
        VK_CONTROL = 0x11
        VK_MENU = 0x12     # Alt
        VK_SHIFT = 0x10
        VK_C = 0x43
        KEYEVENTF_KEYUP = 0x0002

        # 1. Liberar explícitamente Alt, Ctrl y Shift por si el usuario los sigue presionando físicamente
        ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)

        # 2. Pulsar Ctrl+C limpio
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.01)
        ctypes.windll.user32.keybd_event(VK_C, 0, 0, 0)
        time.sleep(0.02)
        ctypes.windll.user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)

    elif SISTEMA == "Darwin":
        from pynput.keyboard import Controller, Key
        teclado = Controller()
        teclado.release(Key.alt)
        teclado.release(Key.cmd)
        time.sleep(0.02)
        teclado.press(Key.cmd)
        teclado.press("c")
        teclado.release("c")
        teclado.release(Key.cmd)
    else:
        from pynput.keyboard import Controller, Key
        teclado = Controller()
        teclado.release(Key.alt)
        teclado.release(Key.ctrl)
        time.sleep(0.02)
        teclado.press(Key.ctrl)
        teclado.press("c")
        teclado.release("c")
        teclado.release(Key.ctrl)


def capturar_seleccion(max_espera_ms: int = 600) -> Optional[str]:
    """Captura el texto seleccionado simulando Ctrl+C.

    1. Guarda el contenido actual del portapapeles
    2. Limpia el portapapeles temporalmente para detectar la nueva copia
    3. Simula Ctrl+C
    4. Espera a que el portapapeles contenga texto
    5. Restaura el contenido anterior si correspondía

    Returns:
        El texto seleccionado, o None si no hay selección.
    """
    try:
        # Guardar portapapeles actual
        try:
            anterior = pyperclip.paste()
        except Exception:
            anterior = ""

        # Limpiar portapapeles para detectar inequívocamente si Ctrl+C copió algo nuevo
        try:
            pyperclip.copy("")
        except Exception:
            pass

        # Pequeña pausa para asegurar que el sistema procese la limpieza
        time.sleep(0.04)

        # Simular Ctrl+C limpio
        _simular_copiar()

        # Esperar a que el portapapeles contenga el nuevo texto
        inicio = time.time()
        intervalo = 0.03  # 30ms
        max_seg = max_espera_ms / 1000.0
        nuevo = ""

        while time.time() - inicio < max_seg:
            time.sleep(intervalo)
            try:
                nuevo = pyperclip.paste()
            except Exception:
                continue
            if nuevo and nuevo.strip():
                break

        # Si la simulación no produjo texto, pero el usuario ya tenía texto en el portapapeles
        # (ej. copió manualmente antes de pulsar el atajo):
        if not nuevo or not nuevo.strip():
            if anterior and anterior.strip():
                return anterior.strip()
            return None

        # Restaurar portapapeles anterior en segundo plano tras un breve lapso
        def _restaurar():
            time.sleep(0.6)
            try:
                if anterior and anterior != nuevo:
                    pyperclip.copy(anterior)
            except Exception:
                pass

        threading.Thread(target=_restaurar, daemon=True).start()

        return nuevo.strip()

    except Exception as e:
        logger.error(f"Error capturando selección: {e}")
        return None


class GestorAtajos:
    """Gestiona los atajos globales de teclado."""

    def __init__(self):
        self._listener = None
        self._callbacks: dict[str, Callable] = {}
        self._activo = False
        self._en_curso = False
        self._lock = threading.Lock()

    def registrar(self, atajo: str, callback: Callable):
        """Registra un callback para un atajo."""
        self._callbacks[atajo] = callback

    def _parsear_atajo(self, atajo_str: str):
        """Parsea string de atajo a formato pynput."""
        from pynput.keyboard import Key, KeyCode

        partes = atajo_str.lower().replace(" ", "").split("+")
        teclas = set()

        mapa = {
            "<ctrl>": Key.ctrl_l,
            "<alt>": Key.alt_l,
            "<shift>": Key.shift_l,
            "<cmd>": Key.cmd,
        }

        for parte in partes:
            if parte in mapa:
                teclas.add(mapa[parte])
            elif parte.startswith("<") and parte.endswith(">"):
                nombre = parte[1:-1]
                try:
                    teclas.add(getattr(Key, nombre))
                except AttributeError:
                    teclas.add(KeyCode.from_char(nombre))
            else:
                teclas.add(KeyCode.from_char(parte))

        return frozenset(teclas)

    def iniciar(self):
        """Inicia la escucha de atajos globales."""
        from pynput.keyboard import GlobalHotKeys

        hotkeys_dict = {}

        for atajo_str, callback in self._callbacks.items():
            def _make_handler(cb):
                def handler():
                    with self._lock:
                        if self._en_curso:
                            return
                        self._en_curso = True
                    try:
                        # Esperar a que se suelten las teclas del atajo
                        time.sleep(0.15)
                        cb()
                    finally:
                        with self._lock:
                            self._en_curso = False
                return handler

            hotkeys_dict[atajo_str] = _make_handler(callback)

        self._listener = GlobalHotKeys(hotkeys_dict)
        self._listener.daemon = True
        self._listener.start()
        self._activo = True
        logger.info("Atajos globales activados")

    def detener(self):
        """Detiene la escucha de atajos."""
        if self._listener:
            self._listener.stop()
            self._activo = False
            logger.info("Atajos globales desactivados")
