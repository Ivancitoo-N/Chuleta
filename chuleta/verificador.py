"""Verificador de respuestas por código (sin llamar al modelo)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from .config import Config
from .extraccion import Fragmento
from .generacion import RespuestaModelo

logger = logging.getLogger("chuleta.verificador")


def _normalizar_para_comparar(texto: str) -> str:
    """Normaliza texto para comparación: minúsculas, sin tildes, espacios normalizados."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _cita_en_fragmento(evidencia: str, texto_fragmento: str) -> bool:
    """Verifica que cada tramo de la evidencia aparezca literalmente en el fragmento.

    Si la evidencia contiene " ... ", verifica cada tramo por separado.
    """
    tramos = evidencia.split(" ... ")

    for tramo in tramos:
        tramo = tramo.strip()
        if not tramo:
            continue

        tramo_norm = _normalizar_para_comparar(tramo)
        texto_norm = _normalizar_para_comparar(texto_fragmento)

        if tramo_norm not in texto_norm:
            return False

    return True


def detectar_opciones(texto: str) -> List[str]:
    """Detecta las letras de opciones presentes en el texto (ej. a, b, c, d, e, f, g...)."""
    opciones = set()

    # Patrón 1: opción al inicio de línea – a), a., A), A.
    for m in re.finditer(r"(?:^|\n)\s*([a-zA-Z])[.)]\s", texto):
        opciones.add(m.group(1).lower())

    # Patrón 2: opciones inline tras coma/punto y coma – , b) texto ; c) texto
    for m in re.finditer(r"[,;]\s*([a-zA-Z])[.)]\s", texto):
        opciones.add(m.group(1).lower())

    # Patrón 3: opciones inline consecutivas sin separador de línea
    #   "a) texto b) texto c) texto" (captura la letra antes del delimitador)
    for m in re.finditer(r"(?<=[.?!\"')\s])\s*([a-zA-Z])[.)]\s", texto):
        letra = m.group(1).lower()
        # Filtrar falsos positivos: solo letras que forman secuencia plausible (a-z)
        if letra <= "z":
            opciones.add(letra)

    # Filtrar: solo conservar letras que formen un rango contiguo desde 'a'
    # para evitar falsos positivos con letras sueltas en el texto
    if opciones:
        ordenadas = sorted(opciones)
        # Si 'a' está presente, tomar la secuencia contigua desde 'a'
        if "a" in ordenadas:
            resultado = []
            esperada = "a"
            for letra in ordenadas:
                if letra == esperada:
                    resultado.append(letra)
                    esperada = chr(ord(esperada) + 1)
                # Si hay un hueco, detenemos (evita falsos positivos lejanos)
            return resultado
        # Si no hay 'a', devolver todas las encontradas (caso raro)
        return ordenadas

    return sorted(opciones)


def verificar(
    respuesta: RespuestaModelo,
    fragmentos: List[Fragmento],
    cfg: Config,
    texto_pregunta: str = "",
) -> Tuple[bool, str]:
    """Verifica la respuesta del modelo por código.

    Returns:
        (es_valida, razon): True si pasa, False con la razón del fallo.
    """
    # 1. JSON inválido o encontrada=false
    if not respuesta.encontrada:
        return False, "encontrada=false"

    # 2. Evidencia vacía o muy corta
    if not respuesta.evidencia:
        return False, "evidencia vacía"

    if len(respuesta.evidencia.strip()) < cfg.verificacion.evidencia_min_chars:
        return False, (
            f"evidencia muy corta ({len(respuesta.evidencia.strip())} < "
            f"{cfg.verificacion.evidencia_min_chars} chars)"
        )

    # 3. Verificar que la evidencia aparece en el fragmento citado
    idx_fragmento = respuesta.fragmento - 1  # F1 = índice 0
    if idx_fragmento < 0 or idx_fragmento >= len(fragmentos):
        return False, f"fragmento {respuesta.fragmento} fuera de rango"

    fragmento_citado = fragmentos[idx_fragmento]
    if not _cita_en_fragmento(respuesta.evidencia, fragmento_citado.texto):
        # En preguntas de esquemas visuales o relaciones de columnas, permitir citas parciales si contiene términos clave
        ev_palabras = [p for p in _normalizar_para_comparar(respuesta.evidencia).split() if len(p) > 3]
        texto_norm = _normalizar_para_comparar(fragmento_citado.texto)
        coincidentes = sum(1 for p in ev_palabras if p in texto_norm)
        if not ev_palabras or (coincidentes / len(ev_palabras)) < 0.6:
            return False, "evidencia no es cita literal del fragmento"

    # 4. En preguntas de opciones, verificar que la opción dada sea coherente
    opciones_detectadas = detectar_opciones(texto_pregunta)
    if opciones_detectadas and len(opciones_detectadas) >= 2:
        if respuesta.opcion is None:
            return False, "pregunta de opciones pero opcion es null"
        opcion_dada = respuesta.opcion.strip().lower()
        if opcion_dada not in opciones_detectadas:
            # Válvula de seguridad: si la opción es la siguiente letra tras
            # el rango detectado (ej. detectó a-d y modelo dice 'e'), aceptar
            # con aviso — la extracción de texto pudo perder opciones.
            ultima = opciones_detectadas[-1]
            siguiente = chr(ord(ultima) + 1)
            if opcion_dada == siguiente and opcion_dada <= "z":
                logger.info(
                    f"Opción '{opcion_dada}' no detectada explícitamente pero "
                    f"es adyacente al rango {opciones_detectadas}; se acepta."
                )
            else:
                return False, (
                    f"opción '{opcion_dada}' no está entre las detectadas: "
                    f"{opciones_detectadas}"
                )

    return True, "OK"


# ─────────── Caché ───────────

class CacheRespuestas:
    """Caché de respuestas por (pregunta normalizada + modo + versión del índice)."""

    def __init__(self):
        self._cache: Dict[str, dict] = {}
        self._version_indice: int = 0

    def _clave(self, pregunta: str, modo: str) -> str:
        """Genera clave de caché."""
        norm = _normalizar_para_comparar(pregunta)
        raw = f"{norm}|{modo}|{self._version_indice}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def actualizar_version(self, version: int):
        """Actualiza la versión del índice (invalida la caché si cambió)."""
        if version != self._version_indice:
            self._cache.clear()
            self._version_indice = version

    def obtener(self, pregunta: str, modo: str) -> Optional[dict]:
        """Busca en caché. Devuelve el resultado o None."""
        clave = self._clave(pregunta, modo)
        return self._cache.get(clave)

    def guardar(self, pregunta: str, modo: str, resultado: dict):
        """Guarda un resultado en caché."""
        clave = self._clave(pregunta, modo)
        self._cache[clave] = resultado

    def limpiar(self):
        """Limpia toda la caché."""
        self._cache.clear()
