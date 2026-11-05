"""Carga de configuración desde config.toml y variables de entorno."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv


def _raiz() -> Path:
    """Devuelve la raíz del proyecto (donde está config.toml)."""
    # Si estamos empaquetados, subimos desde chuleta/
    paquete = Path(__file__).resolve().parent
    raiz = paquete.parent
    if (raiz / "config.toml").exists():
        return raiz
    # Fallback: directorio actual
    cwd = Path.cwd()
    if (cwd / "config.toml").exists():
        return cwd
    return raiz


RAIZ = _raiz()
DIR_DOCUMENTOS = RAIZ / "documentos"
DIR_INDICE = RAIZ / ".indice"
ARCHIVO_CONFIG = RAIZ / "config.toml"
ARCHIVO_LOG = RAIZ / "chuleta.log"


@dataclass
class Atajos:
    responder: str = "<ctrl>+<alt>+q"
    repasar: str = "<ctrl>+<alt>+e"
    captura: str = "<ctrl>+<alt>+s"


@dataclass
class Busqueda:
    top_k: int = 6
    umbral_semantico: float = 0.55
    umbral_lexico: float = 0.15
    chunk_chars: int = 800
    chunk_overlap: int = 150


@dataclass
class Modelos:
    chat: str = "gemini-3.5-flash-lite"
    embeddings: str = "gemini-embedding-001"
    dimensiones: int = 768


@dataclass
class Limites:
    chat_rpm: int = 12
    embed_rpm: int = 80
    concurrencia: int = 1
    max_tokens_por_minuto: int = 20000
    reintentos_max: int = 3


@dataclass
class Verificacion:
    evidencia_min_chars: int = 15
    verificacion_modelo: bool = False


@dataclass
class Cuadro:
    segundos_min: float = 3.0
    segundos_max: float = 15.0
    segundos_por_palabra: float = 0.35
    ancho: int = 380
    opacidad: float = 0.93


@dataclass
class Test:
    activado: bool = True
    segundos_por_pregunta: float = 1.5
    segundos_max_test: float = 45.0
    max_preguntas: int = 50
    concurrencia: int = 1
    lote_max: int = 15


@dataclass
class Config:
    atajos: Atajos = field(default_factory=Atajos)
    busqueda: Busqueda = field(default_factory=Busqueda)
    modelos: Modelos = field(default_factory=Modelos)
    limites: Limites = field(default_factory=Limites)
    verificacion: Verificacion = field(default_factory=Verificacion)
    cuadro: Cuadro = field(default_factory=Cuadro)
    test: Test = field(default_factory=Test)
    api_key: Optional[str] = None


def _aplicar_dict(obj, datos: dict):
    """Aplica los valores de un dict a un dataclass."""
    for k, v in datos.items():
        if hasattr(obj, k):
            setattr(obj, k, v)


def cargar_config() -> Config:
    """Carga la configuración desde config.toml y .env."""
    # Cargar .env
    env_path = RAIZ / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    cfg = Config()
    cfg.api_key = os.environ.get("GEMINI_API_KEY")

    # Cargar TOML
    if ARCHIVO_CONFIG.exists():
        with open(ARCHIVO_CONFIG, "rb") as f:
            datos = tomllib.load(f)
        if "atajos" in datos:
            _aplicar_dict(cfg.atajos, datos["atajos"])
        if "busqueda" in datos:
            _aplicar_dict(cfg.busqueda, datos["busqueda"])
        if "modelos" in datos:
            _aplicar_dict(cfg.modelos, datos["modelos"])
        if "limites" in datos:
            _aplicar_dict(cfg.limites, datos["limites"])
        if "verificacion" in datos:
            _aplicar_dict(cfg.verificacion, datos["verificacion"])
        if "cuadro" in datos:
            _aplicar_dict(cfg.cuadro, datos["cuadro"])
        if "test" in datos:
            _aplicar_dict(cfg.test, datos["test"])

        # Compatibilidad con claves planas si se definen en la raíz
        if "limite_chat_rpm" in datos:
            cfg.limites.chat_rpm = datos["limite_chat_rpm"]
        if "limite_embed_rpm" in datos:
            cfg.limites.embed_rpm = datos["limite_embed_rpm"]
        if "concurrencia" in datos:
            cfg.limites.concurrencia = datos["concurrencia"]
            cfg.test.concurrencia = datos["concurrencia"]

    return cfg
