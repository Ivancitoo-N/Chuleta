"""Recuperación híbrida: semántica (coseno) + léxica (BM25) con fusión RRF."""

from __future__ import annotations

import logging
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from .config import Config
from .extraccion import Fragmento
from .indexado import Indice

logger = logging.getLogger("chuleta.recuperacion")


# ─────────── BM25 propio ───────────

def _normalizar_texto_bm25(texto: str) -> str:
    """Normaliza para BM25: minúsculas, sin tildes ni signos."""
    texto = texto.lower()
    # Quitar tildes
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    # Solo letras, números y espacios
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _tokenizar(texto: str) -> List[str]:
    """Tokeniza texto normalizado en palabras."""
    return _normalizar_texto_bm25(texto).split()


class BM25:
    """Implementación BM25 sencilla para español."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs_tokens: List[List[str]] = []
        self.doc_lens: List[int] = []
        self.avgdl: float = 0
        self.n_docs: int = 0
        self.df: dict[str, int] = {}  # document frequency
        self.idf: dict[str, float] = {}

    def indexar(self, documentos: List[str]):
        """Indexa una lista de documentos (textos)."""
        self.docs_tokens = [_tokenizar(doc) for doc in documentos]
        self.doc_lens = [len(tokens) for tokens in self.docs_tokens]
        self.n_docs = len(documentos)
        self.avgdl = sum(self.doc_lens) / max(self.n_docs, 1)

        # Calcular DF
        self.df = {}
        for tokens in self.docs_tokens:
            for token in set(tokens):
                self.df[token] = self.df.get(token, 0) + 1

        # Calcular IDF
        self.idf = {}
        for term, df in self.df.items():
            self.idf[term] = math.log(
                (self.n_docs - df + 0.5) / (df + 0.5) + 1
            )

    def puntuar(self, consulta: str) -> List[float]:
        """Devuelve puntuaciones BM25 para cada documento."""
        tokens_q = _tokenizar(consulta)
        scores = []

        for i, doc_tokens in enumerate(self.docs_tokens):
            score = 0.0
            dl = self.doc_lens[i]
            # Contar frecuencias del documento
            tf: dict[str, int] = {}
            for t in doc_tokens:
                tf[t] = tf.get(t, 0) + 1

            for qt in tokens_q:
                if qt not in self.idf:
                    continue
                f = tf.get(qt, 0)
                numerador = f * (self.k1 + 1)
                denominador = f + self.k1 * (
                    1 - self.b + self.b * dl / max(self.avgdl, 1)
                )
                score += self.idf[qt] * numerador / denominador

            scores.append(score)

        return scores

    def puntuar_normalizado(self, consulta: str) -> List[float]:
        """Puntuaciones BM25 normalizadas a [0, 1]."""
        scores = self.puntuar(consulta)
        if not scores:
            return scores
        max_score = max(scores)
        if max_score <= 0:
            return [0.0] * len(scores)
        return [s / max_score for s in scores]


# ─────────── Búsqueda semántica ───────────

def embeddings_consultas(
    client, textos: List[str], cfg: Config
) -> List[Optional[np.ndarray]]:
    """Genera embeddings para una lista de consultas en UNA SOLA llamada."""
    if not textos:
        return []
    if not client:
        return [None] * len(textos)

    from google.genai import types
    from .limites import ejecutar_con_reintentos

    tokens_est = sum(len(t) // 4 + 1 for t in textos)

    def _llamar():
        return client.models.embed_content(
            model=cfg.modelos.embeddings,
            contents=textos,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=cfg.modelos.dimensiones,
            ),
        )

    try:
        resultado = ejecutar_con_reintentos(
            _llamar, tipo="embeddings", tokens_estimados=tokens_est, cfg=cfg
        )
        vectores: List[Optional[np.ndarray]] = []
        for emb in resultado.embeddings:
            vec = np.array(emb.values, dtype=np.float32)
            norma = np.linalg.norm(vec)
            if norma > 0:
                vec = vec / norma
            vectores.append(vec)
        return vectores
    except Exception as e:
        logger.error(f"Error generando embeddings agrupados: {e}")
        return [None] * len(textos)


def embedding_consulta(
    client, texto: str, cfg: Config
) -> Optional[np.ndarray]:
    """Genera embedding para una consulta individual."""
    vecs = embeddings_consultas(client, [texto], cfg)
    return vecs[0] if vecs else None


def busqueda_semantica(
    query_emb: np.ndarray,
    embeddings: np.ndarray,
) -> List[float]:
    """Similitud coseno entre consulta y todos los fragmentos."""
    if embeddings is None or embeddings.shape[0] == 0 or query_emb is None:
        return []
    scores = embeddings @ query_emb
    return scores.tolist()


# ─────────── Fusión RRF ───────────

def rrf(
    rankings: List[List[Tuple[int, float]]],
    k: int = 60,
) -> List[Tuple[int, float]]:
    """Reciprocal Rank Fusion de múltiples rankings.

    Cada ranking es una lista de (índice, puntuación) ordenada descendente.
    """
    scores: dict[int, float] = {}

    for ranking in rankings:
        for rank, (idx, _score) in enumerate(ranking):
            scores[idx] = scores.get(idx, 0) + 1.0 / (k + rank + 1)

    # Ordenar por score fusionado descendente
    resultado = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return resultado


@dataclass
class ResultadoRecuperacion:
    """Resultado de la búsqueda híbrida."""
    fragmentos: List[Fragmento]
    scores_semanticos: List[float]
    scores_lexicos: List[float]
    scores_fusionados: List[float]
    pasa_umbral: bool


def _es_pregunta_test(texto: str) -> bool:
    """Detecta si el texto tiene opciones tipo test (a/b/c/d/e/f...)."""
    patrones = [
        r"(?:^|\n)\s*[a-zA-Z][.)]\s",
    ]
    for patron in patrones:
        if len(re.findall(patron, texto)) >= 2:
            return True
    return False


def _extraer_enunciado_y_opciones(texto: str) -> Tuple[str, str]:
    """Separa el enunciado de las opciones en una pregunta test."""
    match = re.search(r"(?:^|\n)\s*[aA][.)]\s", texto)
    if match:
        enunciado = texto[:match.start()].strip()
        opciones = texto[match.start():].strip()
        return enunciado, opciones
    return texto, ""


def buscar(
    indice: Indice,
    texto: str,
    cfg: Config,
    client=None,
    query_emb: Optional[np.ndarray] = None,
) -> ResultadoRecuperacion:
    """Búsqueda híbrida: semántica + BM25, fusionada con RRF.

    Si se proporciona `query_emb`, se reutiliza evitando llamadas de red.
    """
    if not indice.fragmentos:
        return ResultadoRecuperacion([], [], [], [], False)

    top_k = cfg.busqueda.top_k
    umbral_sem = cfg.busqueda.umbral_semantico
    umbral_lex = cfg.busqueda.umbral_lexico

    textos_docs = [f.texto for f in indice.fragmentos]

    # BM25
    bm25 = BM25()
    bm25.indexar(textos_docs)

    es_test = _es_pregunta_test(texto)
    rankings_a_fusionar: list[list[tuple[int, float]]] = []
    emb_usado = query_emb

    if es_test:
        enunciado, opciones = _extraer_enunciado_y_opciones(texto)

        # Búsqueda 1: solo enunciado
        scores_bm25_1 = bm25.puntuar_normalizado(enunciado)
        ranking_bm25_1 = sorted(
            enumerate(scores_bm25_1), key=lambda x: x[1], reverse=True
        )
        rankings_a_fusionar.append(ranking_bm25_1)

        # Búsqueda 2: enunciado + opciones
        texto_completo = texto
        scores_bm25_2 = bm25.puntuar_normalizado(texto_completo)
        ranking_bm25_2 = sorted(
            enumerate(scores_bm25_2), key=lambda x: x[1], reverse=True
        )
        rankings_a_fusionar.append(ranking_bm25_2)

        if client and indice.embeddings is not None:
            if emb_usado is None:
                emb_usado = embedding_consulta(client, texto_completo, cfg)
            if emb_usado is not None:
                scores_sem = busqueda_semantica(emb_usado, indice.embeddings)
                ranking_sem = sorted(
                    enumerate(scores_sem), key=lambda x: x[1], reverse=True
                )
                rankings_a_fusionar.append(ranking_sem)
    else:
        # Búsqueda normal
        scores_bm25 = bm25.puntuar_normalizado(texto)
        ranking_bm25 = sorted(
            enumerate(scores_bm25), key=lambda x: x[1], reverse=True
        )
        rankings_a_fusionar.append(ranking_bm25)

        if client and indice.embeddings is not None:
            if emb_usado is None:
                emb_usado = embedding_consulta(client, texto, cfg)
            if emb_usado is not None:
                scores_sem = busqueda_semantica(emb_usado, indice.embeddings)
                ranking_sem = sorted(
                    enumerate(scores_sem), key=lambda x: x[1], reverse=True
                )
                rankings_a_fusionar.append(ranking_sem)

    # Fusión RRF
    fusionado = rrf(rankings_a_fusionar)

    # Top K
    top_indices = [idx for idx, _ in fusionado[:top_k]]

    # Recalcular scores para los seleccionados reutilizando el embedding
    scores_bm25_final = bm25.puntuar_normalizado(texto)

    if emb_usado is not None and indice.embeddings is not None:
        scores_sem_final = busqueda_semantica(emb_usado, indice.embeddings)
    else:
        scores_sem_final = [0.0] * len(indice.fragmentos)

    # Filtro de umbrales
    mejor_sem = max(
        (scores_sem_final[i] for i in top_indices), default=0
    )
    mejor_lex = max(
        (scores_bm25_final[i] for i in top_indices), default=0
    )
    pasa_umbral = mejor_sem >= umbral_sem or mejor_lex >= umbral_lex

    # Añadir vecinos del mejor resultado
    if top_indices:
        mejor_idx = top_indices[0]
        mejor_frag = indice.fragmentos[mejor_idx]
        vecinos_a_agregar = []

        # Vecino anterior
        if mejor_idx > 0:
            vecino = indice.fragmentos[mejor_idx - 1]
            if (vecino.archivo == mejor_frag.archivo and
                    vecino.pagina == mejor_frag.pagina and
                    (mejor_idx - 1) not in top_indices):
                vecinos_a_agregar.append(mejor_idx - 1)

        # Vecino posterior
        if mejor_idx < len(indice.fragmentos) - 1:
            vecino = indice.fragmentos[mejor_idx + 1]
            if (vecino.archivo == mejor_frag.archivo and
                    vecino.pagina == mejor_frag.pagina and
                    (mejor_idx + 1) not in top_indices):
                vecinos_a_agregar.append(mejor_idx + 1)

        top_indices.extend(vecinos_a_agregar)

    # Construir resultado
    fragmentos_resultado = [indice.fragmentos[i] for i in top_indices]
    sem_resultado = [scores_sem_final[i] for i in top_indices]
    lex_resultado = [scores_bm25_final[i] for i in top_indices]
    fus_resultado = []
    mapa_fusion = dict(fusionado)
    for i in top_indices:
        fus_resultado.append(mapa_fusion.get(i, 0.0))

    return ResultadoRecuperacion(
        fragmentos=fragmentos_resultado,
        scores_semanticos=sem_resultado,
        scores_lexicos=lex_resultado,
        scores_fusionados=fus_resultado,
        pasa_umbral=pasa_umbral,
    )
