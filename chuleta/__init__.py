"""Chuleta – herramienta de estudio que responde preguntas desde tus documentos."""

__version__ = "1.0.0"

try:
    from .captura import habilitar_dpi_awareness
    habilitar_dpi_awareness()
except Exception:
    pass
