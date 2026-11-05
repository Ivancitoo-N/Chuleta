"""Extracción de texto desde PDF, Markdown y TXT, con troceado inteligente."""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("chuleta.extraccion")


@dataclass
class Fragmento:
    """Un trozo de texto con sus metadatos de origen."""
    id: str
    archivo: str
    texto: str
    pagina: Optional[int] = None
    seccion: Optional[str] = None

    def texto_para_embedding(self) -> str:
        """Texto enriquecido para embedding: antepone archivo > sección."""
        prefijo = self.archivo
        if self.seccion:
            prefijo += f" > {self.seccion}"
        elif self.pagina is not None:
            prefijo += f" > p. {self.pagina}"
        return f"{prefijo}\n{self.texto}"


# ─────────── Limpieza de texto ───────────

def limpiar_texto(texto: str) -> str:
    """Limpia el texto extraído: une guiones de fin de línea, normaliza espacios."""
    # Unir palabras partidas por guion a final de línea
    texto = re.sub(r"(\w)-\n(\w)", r"\1\2", texto)
    # Normalizar saltos de línea múltiples a máximo 2
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # Normalizar espacios múltiples a uno
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    # Eliminar espacios al inicio/fin de líneas
    texto = re.sub(r"^ +| +$", "", texto, flags=re.MULTILINE)
    return texto.strip()


def _detectar_cabeceras_pies(paginas: List[str], umbral: int = 3) -> set:
    """Detecta líneas que se repiten en muchas páginas (cabeceras/pies)."""
    if len(paginas) < umbral:
        return set()

    conteo: dict[str, int] = {}
    for pagina_texto in paginas:
        lineas = pagina_texto.strip().split("\n")
        # Solo checar primeras 3 y últimas 3 líneas
        candidatas = set()
        for linea in lineas[:3] + lineas[-3:]:
            linea_limpia = linea.strip()
            if len(linea_limpia) > 3:  # Ignorar líneas muy cortas
                candidatas.add(linea_limpia)
        for c in candidatas:
            conteo[c] = conteo.get(c, 0) + 1

    # Líneas que aparecen en más de la mitad de las páginas
    mitad = len(paginas) / 2
    return {linea for linea, n in conteo.items() if n > mitad}


def _eliminar_cabeceras_pies(texto: str, repetidas: set) -> str:
    """Elimina las líneas que coinciden con cabeceras/pies repetidos."""
    if not repetidas:
        return texto
    lineas = texto.split("\n")
    return "\n".join(l for l in lineas if l.strip() not in repetidas)


# ─────────── Extracción por tipo de archivo ───────────

def extraer_pdf(ruta: Path) -> List[tuple[int, str]]:
    """Extrae texto de un PDF página a página. Devuelve [(nº_página, texto)]."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.error("pypdf no está instalado. Ejecuta: pip install pypdf")
        return []

    try:
        reader = PdfReader(str(ruta))
    except Exception as e:
        logger.error(f"Error al abrir PDF {ruta.name}: {e}")
        return []

    paginas_raw = []
    for i, pagina in enumerate(reader.pages, 1):
        texto = pagina.extract_text() or ""
        paginas_raw.append((i, texto))

    # Verificar si el PDF es escaneado (sin texto extraíble)
    textos_no_vacios = [t for _, t in paginas_raw if t.strip()]
    if not textos_no_vacios:
        logger.warning(f"PDF escaneado (sin texto extraíble): {ruta.name}")
        print(f"⚠ PDF escaneado (sin texto extraíble): {ruta.name}")
        return []

    # Detectar y eliminar cabeceras/pies repetidos
    repetidas = _detectar_cabeceras_pies([t for _, t in paginas_raw])

    resultado = []
    for num_pag, texto in paginas_raw:
        texto = _eliminar_cabeceras_pies(texto, repetidas)
        texto = limpiar_texto(texto)
        if texto:
            resultado.append((num_pag, texto))

    return resultado


def extraer_md(ruta: Path) -> List[tuple[Optional[str], str]]:
    """Extrae texto de un Markdown por secciones. Devuelve [(sección, texto)]."""
    try:
        contenido = ruta.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.error(f"Error al leer {ruta.name}: {e}")
        return []

    secciones = []
    seccion_actual = None
    buffer: list[str] = []

    for linea in contenido.split("\n"):
        match = re.match(r"^(#{1,6})\s+(.+)$", linea)
        if match:
            # Guardar sección anterior
            if buffer:
                texto = limpiar_texto("\n".join(buffer))
                if texto:
                    secciones.append((seccion_actual, texto))
                buffer = []
            seccion_actual = match.group(2).strip()
        else:
            buffer.append(linea)

    # Última sección
    if buffer:
        texto = limpiar_texto("\n".join(buffer))
        if texto:
            secciones.append((seccion_actual, texto))

    return secciones


def extraer_txt(ruta: Path) -> List[tuple[None, str]]:
    """Extrae texto de un TXT por párrafos. Devuelve [(None, texto)]."""
    try:
        contenido = ruta.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.error(f"Error al leer {ruta.name}: {e}")
        return []

    contenido = limpiar_texto(contenido)
    if not contenido:
        return []

    return [(None, contenido)]


# ─────────── Troceado ───────────

def _cortar_por_frase(texto: str, max_chars: int) -> int:
    """Busca el último fin de frase antes de max_chars."""
    if len(texto) <= max_chars:
        return len(texto)

    # Buscar el último punto, signo de interrogación o exclamación seguido de espacio
    patron = re.compile(r"[.!?]\s", re.DOTALL)
    ultimo_corte = max_chars
    for m in patron.finditer(texto[:max_chars]):
        ultimo_corte = m.end()

    # Si no encontramos ningún fin de frase, buscar última coma o punto y coma
    if ultimo_corte == max_chars:
        for m in re.finditer(r"[,;]\s", texto[:max_chars]):
            ultimo_corte = m.end()

    # Si sigue sin encontrar, buscar último espacio
    if ultimo_corte == max_chars:
        ultimo_espacio = texto.rfind(" ", 0, max_chars)
        if ultimo_espacio > max_chars // 2:
            ultimo_corte = ultimo_espacio + 1

    return ultimo_corte


def trocear_texto(
    texto: str,
    chunk_chars: int = 800,
    chunk_overlap: int = 150,
) -> List[str]:
    """Divide texto en fragmentos respetando frases.

    No mezcla párrafos de forma arbitraria; el solape se toma del final
    del fragmento anterior para dar contexto al siguiente.
    """
    if not texto or not texto.strip():
        return []

    if len(texto) <= chunk_chars:
        return [texto]

    fragmentos: list[str] = []
    inicio = 0

    while inicio < len(texto):
        fin = _cortar_por_frase(texto[inicio:], chunk_chars)
        trozo = texto[inicio:inicio + fin].strip()
        if trozo:
            fragmentos.append(trozo)
        if inicio + fin >= len(texto):
            break
        # Retroceder para el solape
        inicio = inicio + fin - chunk_overlap
        if inicio < 0:
            inicio = 0
        # Evitar bucle infinito
        if inicio + fin >= len(texto) and trozo:
            break

    return fragmentos


def trocear_por_parrafos(
    texto: str,
    chunk_chars: int = 800,
    chunk_overlap: int = 150,
) -> List[str]:
    """Trocea respetando párrafos: agrupa párrafos hasta el tamaño objetivo."""
    parrafos = re.split(r"\n\n+", texto)
    fragmentos: list[str] = []
    buffer = ""

    for parrafo in parrafos:
        parrafo = parrafo.strip()
        if not parrafo:
            continue

        if len(buffer) + len(parrafo) + 2 <= chunk_chars:
            buffer = (buffer + "\n\n" + parrafo).strip()
        else:
            if buffer:
                fragmentos.append(buffer)
            # Si el párrafo individual es más grande que chunk_chars, trocearlo
            if len(parrafo) > chunk_chars:
                sub = trocear_texto(parrafo, chunk_chars, chunk_overlap)
                fragmentos.extend(sub)
                buffer = ""
            else:
                # Overlap: tomar las últimas ~overlap chars del buffer anterior
                if fragmentos:
                    overlap_text = fragmentos[-1][-chunk_overlap:]
                    # Cortar en un espacio para no partir palabras
                    idx = overlap_text.find(" ")
                    if idx > 0:
                        overlap_text = overlap_text[idx + 1:]
                    buffer = overlap_text + "\n\n" + parrafo
                else:
                    buffer = parrafo

    if buffer.strip():
        fragmentos.append(buffer.strip())

    return fragmentos


# ─────────── Procesamiento completo ───────────

def hash_contenido(ruta: Path) -> str:
    """Calcula hash SHA256 del contenido de un archivo."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            h.update(bloque)
    return h.hexdigest()


def es_archivo_oculto(ruta: Path) -> bool:
    """Verifica si un archivo o alguna de sus carpetas padre es oculto."""
    for parte in ruta.parts:
        if parte.startswith(".") and parte not in (".", ".."):
            return True
    return False


def listar_documentos(dir_docs: Path) -> List[Path]:
    """Lista todos los documentos válidos (PDF, MD, TXT) en la carpeta."""
    extensiones = {".pdf", ".md", ".txt"}
    archivos = []

    if not dir_docs.exists():
        dir_docs.mkdir(parents=True, exist_ok=True)
        return archivos

    for ruta in dir_docs.rglob("*"):
        if ruta.is_file() and ruta.suffix.lower() in extensiones:
            # Ignorar archivos ocultos
            relativa = ruta.relative_to(dir_docs)
            if not es_archivo_oculto(relativa):
                archivos.append(ruta)

    return sorted(archivos)


def procesar_archivo(
    ruta: Path,
    dir_docs: Path,
    chunk_chars: int = 800,
    chunk_overlap: int = 150,
) -> List[Fragmento]:
    """Procesa un archivo y devuelve sus fragmentos."""
    nombre_rel = str(ruta.relative_to(dir_docs)).replace("\\", "/")
    ext = ruta.suffix.lower()
    fragmentos: list[Fragmento] = []
    contador = 0

    if ext == ".pdf":
        paginas = extraer_pdf(ruta)
        for num_pag, texto in paginas:
            trozos = trocear_por_parrafos(texto, chunk_chars, chunk_overlap)
            for trozo in trozos:
                fid = f"{nombre_rel}:{num_pag}:{contador}"
                fragmentos.append(Fragmento(
                    id=fid,
                    archivo=nombre_rel,
                    texto=trozo,
                    pagina=num_pag,
                ))
                contador += 1

    elif ext == ".md":
        secciones = extraer_md(ruta)
        for seccion, texto in secciones:
            trozos = trocear_por_parrafos(texto, chunk_chars, chunk_overlap)
            for trozo in trozos:
                fid = f"{nombre_rel}:{seccion or 'intro'}:{contador}"
                fragmentos.append(Fragmento(
                    id=fid,
                    archivo=nombre_rel,
                    texto=trozo,
                    seccion=seccion,
                ))
                contador += 1

    elif ext == ".txt":
        bloques = extraer_txt(ruta)
        for _, texto in bloques:
            trozos = trocear_por_parrafos(texto, chunk_chars, chunk_overlap)
            for trozo in trozos:
                fid = f"{nombre_rel}::{contador}"
                fragmentos.append(Fragmento(
                    id=fid,
                    archivo=nombre_rel,
                    texto=trozo,
                ))
                contador += 1

    return fragmentos
