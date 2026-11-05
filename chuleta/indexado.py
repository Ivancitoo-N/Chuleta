"""Indexado de documentos con embeddings y metadatos. Reindexado incremental."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

import numpy as np

from .config import Config, DIR_DOCUMENTOS, DIR_INDICE
from .extraccion import (
    Fragmento, listar_documentos, procesar_archivo, hash_contenido,
)

logger = logging.getLogger("chuleta.indexado")

ARCHIVO_META = "metadatos.json"
ARCHIVO_EMBEDDINGS = "embeddings.npy"
ARCHIVO_HASHES = "hashes.json"


class Indice:
    """Índice de fragmentos con embeddings y metadatos."""

    def __init__(self, cfg: Config, client=None):
        self.cfg = cfg
        self.client = client
        self.fragmentos: List[Fragmento] = []
        self.embeddings: Optional[np.ndarray] = None
        self.hashes: Dict[str, str] = {}
        self.version: int = 0
        self._dir = DIR_INDICE

    def _ruta(self, nombre: str) -> Path:
        return self._dir / nombre

    def cargar(self) -> bool:
        """Carga el índice desde disco. Devuelve True si existía."""
        if not self._dir.exists():
            return False

        meta_path = self._ruta(ARCHIVO_META)
        emb_path = self._ruta(ARCHIVO_EMBEDDINGS)
        hash_path = self._ruta(ARCHIVO_HASHES)

        if not meta_path.exists() or not emb_path.exists():
            return False

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                datos = json.load(f)

            self.fragmentos = [
                Fragmento(**frag) for frag in datos.get("fragmentos", [])
            ]
            self.version = datos.get("version", 0)
            self.embeddings = np.load(str(emb_path))

            if hash_path.exists():
                with open(hash_path, "r", encoding="utf-8") as f:
                    self.hashes = json.load(f)

            logger.info(
                f"Índice cargado: {len(self.fragmentos)} fragmentos, "
                f"versión {self.version}"
            )
            return True
        except Exception as e:
            logger.error(f"Error al cargar índice: {e}")
            return False

    def guardar(self, guardar_hashes: bool = True):
        """Guarda el índice a disco.
        
        Args:
            guardar_hashes: Si False, no escribe hashes.json (para guardados
                parciales durante indexación progresiva).
        """
        self._dir.mkdir(parents=True, exist_ok=True)

        meta = {
            "version": self.version,
            "fragmentos": [
                {
                    "id": f.id,
                    "archivo": f.archivo,
                    "texto": f.texto,
                    "pagina": f.pagina,
                    "seccion": f.seccion,
                }
                for f in self.fragmentos
            ],
        }

        with open(self._ruta(ARCHIVO_META), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)

        if self.embeddings is not None:
            np.save(str(self._ruta(ARCHIVO_EMBEDDINGS)), self.embeddings)

        if guardar_hashes:
            with open(self._ruta(ARCHIVO_HASHES), "w", encoding="utf-8") as f:
                json.dump(self.hashes, f, ensure_ascii=False, indent=1)

    def _generar_embeddings_controlado(
        self,
        frags_nuevos: List[Fragmento],
        frags_base: List[Fragmento],
        embs_base: Optional[np.ndarray],
    ) -> Tuple[List[Fragmento], np.ndarray, Optional[str]]:
        """Genera embeddings en lotes pequeños controlados por tokens con reanudación y barra de progreso.

        Devuelve: (fragmentos_acumulados, embeddings_acumulados, aviso_error)
        """
        import sys

        # Detectar si stdout está disponible (pythonw.exe lo pone a None)
        _tiene_consola = (
            sys.stdout is not None and hasattr(sys.stdout, "write")
        )

        def _progreso(msg: str, *, newline: bool = True, overwrite: bool = False):
            """Escribe progreso a consola si está disponible; si no, usa logger."""
            if _tiene_consola:
                if overwrite:
                    sys.stdout.write(msg)
                    sys.stdout.flush()
                else:
                    print(msg)
            else:
                # Sin consola: registrar solo mensajes sustanciales (no barras)
                texto_limpio = msg.strip("\r\n ")
                if texto_limpio and not overwrite:
                    logger.info(texto_limpio)

        dim = self.cfg.modelos.dimensiones

        if not frags_nuevos:
            embs = embs_base if embs_base is not None else np.zeros((0, dim), dtype=np.float32)
            return frags_base, embs, None

        if not self.client:
            embs_nuevos = np.zeros((len(frags_nuevos), dim), dtype=np.float32)
            if embs_base is not None and len(embs_base) > 0:
                return frags_base + frags_nuevos, np.vstack([embs_base, embs_nuevos]), None
            return frags_base + frags_nuevos, embs_nuevos, None

        from google.genai import types
        from .limites import (
            ejecutar_con_reintentos,
            CuotaDiariaAgotadaError,
            LimiteMinutoError,
        )

        # Lotes pequeños limitados por tokens (máx 15 fragmentos o ~3500 tokens por lote)
        lotes: list[list[Fragmento]] = []
        lote_actual: list[Fragmento] = []
        tokens_lote_actual = 0
        MAX_TOKENS_LOTE = 3500
        MAX_FRAGS_LOTE = 15

        for f in frags_nuevos:
            tok_f = len(f.texto_para_embedding()) // 4 + 1
            if lote_actual and (
                len(lote_actual) >= MAX_FRAGS_LOTE
                or tokens_lote_actual + tok_f > MAX_TOKENS_LOTE
            ):
                lotes.append(lote_actual)
                lote_actual = []
                tokens_lote_actual = 0
            lote_actual.append(f)
            tokens_lote_actual += tok_f

        if lote_actual:
            lotes.append(lote_actual)

        frags_acumulados = list(frags_base)
        embs_acumulados = embs_base
        total_nuevos = len(frags_nuevos)
        procesados = 0
        aviso_parcial = None

        _progreso(
            f"  Indexando {total_nuevos} fragmentos a ritmo controlado "
            f"({len(lotes)} lotes, max ~20.000 tokens/min)..."
        )

        for idx_lote, lote in enumerate(lotes, 1):
            textos_lote = [f.texto_para_embedding() for f in lote]
            tokens_est = sum(len(t) // 4 + 1 for t in textos_lote)

            def _llamar():
                return self.client.models.embed_content(
                    model=self.cfg.modelos.embeddings,
                    contents=textos_lote,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=self.cfg.modelos.dimensiones,
                    ),
                )

            try:
                res = ejecutar_con_reintentos(
                    _llamar,
                    tipo="embeddings",
                    tokens_estimados=tokens_est,
                    cfg=self.cfg,
                )
                vectores = []
                for emb in res.embeddings:
                    vec = np.array(emb.values, dtype=np.float32)
                    norma = np.linalg.norm(vec)
                    if norma > 0:
                        vec = vec / norma
                    vectores.append(vec)

                matriz_lote = np.array(vectores, dtype=np.float32)

                frags_acumulados.extend(lote)
                if embs_acumulados is not None and len(embs_acumulados) > 0:
                    embs_acumulados = np.vstack([embs_acumulados, matriz_lote])
                else:
                    embs_acumulados = matriz_lote

                procesados += len(lote)

                # Reanudación: guardar inmediatamente lo acumulado hasta este lote
                # NO guardar hashes para evitar marcar el archivo como completado
                self.fragmentos = frags_acumulados
                self.embeddings = embs_acumulados
                self.guardar(guardar_hashes=False)

                # Barra de progreso en consola (se omite en modo sin consola)
                pct = (procesados / total_nuevos) * 100
                ancho = 20
                lleno = int(ancho * procesados / total_nuevos)
                barra = "=" * lleno + (" " * (ancho - lleno))
                _progreso(
                    f"\r  [{barra}] {pct:3.0f}% ({procesados}/{total_nuevos} fragmentos)",
                    overwrite=True,
                )

            except (CuotaDiariaAgotadaError, LimiteMinutoError) as e:
                logger.warning(
                    f"Indexación pausada por cuota ({e}). Progreso guardado."
                )
                aviso_parcial = (
                    f"Límite alcanzado: {e} Progreso guardado "
                    f"({procesados}/{total_nuevos} fragmentos)."
                )
                _progreso(f"\n  [PAUSA] {aviso_parcial}")
                break
            except Exception as e:
                logger.error(f"Error en lote {idx_lote}: {e}")
                aviso_parcial = (
                    f"Error en indexación: {e}. Progreso guardado "
                    f"({procesados}/{total_nuevos})."
                )
                _progreso(f"\n  [ERROR] {aviso_parcial}")
                break

        _progreso("")
        return frags_acumulados, embs_acumulados, aviso_parcial

    def _generar_embeddings(self, textos: List[str]) -> np.ndarray:
        """Compatibilidad con tests y llamadas directas."""
        from .recuperacion import embeddings_consultas
        vectores = embeddings_consultas(self.client, textos, self.cfg)
        dim = self.cfg.modelos.dimensiones
        matriz = np.array(
            [v if v is not None else np.zeros(dim, dtype=np.float32) for v in vectores],
            dtype=np.float32,
        )
        return matriz

    def indexar(self, forzar: bool = False) -> dict:
        """Indexa los documentos a ritmo controlado con soporte de reanudación."""
        dir_docs = DIR_DOCUMENTOS
        dir_docs.mkdir(parents=True, exist_ok=True)

        archivos = listar_documentos(dir_docs)
        stats = {
            "archivos_total": len(archivos),
            "nuevos": 0,
            "modificados": 0,
            "borrados": 0,
            "fragmentos_total": 0,
            "avisos": [],
        }

        # Calcular hashes actuales
        hashes_actuales: Dict[str, str] = {}
        for ruta in archivos:
            nombre_rel = str(ruta.relative_to(dir_docs)).replace("\\", "/")
            hashes_actuales[nombre_rel] = hash_contenido(ruta)

        if not forzar and self.hashes:
            archivos_anteriores = set(self.hashes.keys())
            archivos_nuevos_set = set(hashes_actuales.keys())

            borrados = archivos_anteriores - archivos_nuevos_set
            nuevos = archivos_nuevos_set - archivos_anteriores
            comunes = archivos_anteriores & archivos_nuevos_set
            modificados = {
                a for a in comunes
                if self.hashes[a] != hashes_actuales[a]
            }

            # Verificación de integridad: comprobar que los fragmentos almacenados
            # cubren realmente todos los archivos. Si hay muchos menos fragmentos
            # de los esperados, forzar reindexado.
            indice_integro = True
            if not borrados and not nuevos and not modificados and self.fragmentos:
                # Regenerar fragmentos esperados y comparar cuenta
                frags_esperados_total = 0
                for ruta in archivos:
                    nombre_rel = str(ruta.relative_to(dir_docs)).replace("\\", "/")
                    frags_esperados = procesar_archivo(
                        ruta, dir_docs,
                        self.cfg.busqueda.chunk_chars,
                        self.cfg.busqueda.chunk_overlap,
                    )
                    frags_esperados_total += len(frags_esperados)

                if len(self.fragmentos) >= frags_esperados_total:
                    stats["fragmentos_total"] = len(self.fragmentos)
                    logger.info("Índice al día, sin cambios.")
                    return stats
                else:
                    logger.warning(
                        f"Índice incompleto: {len(self.fragmentos)} fragmentos "
                        f"de {frags_esperados_total} esperados. Forzando reindexado."
                    )
                    indice_integro = False

            if not indice_integro:
                # Forzar reindexado completo
                a_procesar = set(hashes_actuales.keys())
                frags_mantener = []
                embs_base = np.zeros((0, self.cfg.modelos.dimensiones), dtype=np.float32)
                stats["nuevos"] = len(a_procesar)
                stats["modificados"] = 0
                stats["borrados"] = 0
            else:
                stats["nuevos"] = len(nuevos)
                stats["modificados"] = len(modificados)
                stats["borrados"] = len(borrados)

                a_procesar = nuevos | modificados
                frags_mantener = [
                    f for f in self.fragmentos
                    if f.archivo not in (borrados | a_procesar)
                ]
                embs_mantener_idx = [
                    i for i, f in enumerate(self.fragmentos)
                    if f.archivo not in (borrados | a_procesar)
                ]
                if embs_mantener_idx and self.embeddings is not None:
                    embs_base = self.embeddings[embs_mantener_idx]
                else:
                    embs_base = np.zeros((0, self.cfg.modelos.dimensiones), dtype=np.float32)
        else:
            a_procesar = set(hashes_actuales.keys())
            frags_mantener = []
            embs_base = np.zeros((0, self.cfg.modelos.dimensiones), dtype=np.float32)
            stats["nuevos"] = len(a_procesar)

        # Reanudación: identificar qué fragmentos de a_procesar ya están en el índice actual
        ids_existentes = {
            f.id: i for i, f in enumerate(self.fragmentos)
            if self.embeddings is not None and i < len(self.embeddings)
        }

        frags_nuevos_pendientes: list[Fragmento] = []
        for ruta in archivos:
            nombre_rel = str(ruta.relative_to(dir_docs)).replace("\\", "/")
            if nombre_rel in a_procesar:
                nuevos_frags = procesar_archivo(
                    ruta, dir_docs,
                    self.cfg.busqueda.chunk_chars,
                    self.cfg.busqueda.chunk_overlap,
                )
                if not nuevos_frags and ruta.suffix.lower() == ".pdf":
                    stats["avisos"].append(f"PDF escaneado: {ruta.name}")

                for nf in nuevos_frags:
                    if not forzar and nf.id in ids_existentes:
                        # Ya estaba indexado en una ejecución previa interrumpida: reanudar
                        idx_ex = ids_existentes[nf.id]
                        frags_mantener.append(nf)
                        if self.embeddings is not None and idx_ex < len(self.embeddings):
                            vec_ex = self.embeddings[idx_ex:idx_ex + 1]
                            embs_base = np.vstack([embs_base, vec_ex]) if len(embs_base) > 0 else vec_ex
                    else:
                        frags_nuevos_pendientes.append(nf)

        # Indexación controlada por lotes con reanudación
        frags_totales, embs_totales, aviso = self._generar_embeddings_controlado(
            frags_nuevos_pendientes, frags_mantener, embs_base
        )

        if aviso:
            stats["avisos"].append(aviso)

        self.fragmentos = frags_totales
        self.embeddings = embs_totales

        # Solo marcamos como completados los hashes cuyos fragmentos no quedaron pendientes
        if not aviso:
            self.hashes = hashes_actuales
            self.version += 1

        stats["fragmentos_total"] = len(self.fragmentos)
        self.guardar()
        return stats
