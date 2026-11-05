"""Orquestador principal de Chuleta."""

from __future__ import annotations

import logging
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Optional

from .config import Config, cargar_config, ARCHIVO_LOG
from .indexado import Indice
from .recuperacion import buscar
from .generacion import generar_respuesta
from .verificador import verificar, CacheRespuestas
from .modo_test import es_modo_test, separar_preguntas, procesar_test, formatear_resultados_test
from .cuadro import CuadroRespuesta
from .captura import GestorAtajos, capturar_seleccion, habilitar_dpi_awareness
from .bandeja import Bandeja
from .limites import contador_uso, CuotaDiariaAgotadaError, LimiteMinutoError

logger = logging.getLogger("chuleta")


def _configurar_logging():
    """Configura el logging a archivo."""
    handler = logging.FileHandler(str(ARCHIVO_LOG), encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    logging.getLogger("chuleta").addHandler(handler)
    logging.getLogger("chuleta").setLevel(logging.DEBUG)


def _crear_cliente(cfg: Config):
    """Crea el cliente de Gemini."""
    if not cfg.api_key:
        return None

    from google import genai
    return genai.Client(api_key=cfg.api_key)


class App:
    """Aplicación principal de Chuleta."""

    def __init__(self):
        self.cfg: Config = cargar_config()
        self.client = None
        self.indice: Indice = Indice(self.cfg)
        self.cache = CacheRespuestas()
        self._cache_fragmentos: dict[str, tuple[float, Any]] = {}
        self.cuadro: Optional[CuadroRespuesta] = None
        self.gestor_atajos: Optional[GestorAtajos] = None
        self.bandeja: Optional[Bandeja] = None
        self._root: Optional[tk.Tk] = None

    def iniciar(self):
        """Inicia la aplicación completa."""
        _configurar_logging()
        logger.info("Iniciando Chuleta...")

        # Cliente Gemini
        self.client = _crear_cliente(self.cfg)
        if not self.client:
            logger.warning("Sin clave de API. Funcionalidad limitada.")

        # Índice
        self.indice = Indice(self.cfg, self.client)
        self.indice.cargar()
        try:
            stats = self.indice.indexar()
            logger.info(f"Indexado: {stats}")
        except Exception as e:
            logger.error(f"Error en indexado: {e}")

        self.cache.actualizar_version(self.indice.version)

        # Habilitar DPI awareness en Windows antes de inicializar tkinter
        habilitar_dpi_awareness()

        # Crear root de tkinter (oculto)
        self._root = tk.Tk()
        self._root.withdraw()  # Ocultar ventana principal
        self._root.title("Chuleta")

        # Cuadro de respuesta
        self.cuadro = CuadroRespuesta(self.cfg)
        self.cuadro.inicializar(self._root)

        # Selector de recuadro para captura de pantalla / esquemas
        from .recuadro import SelectorRecuadro
        self.selector_recuadro = SelectorRecuadro(self._root)

        # Atajos globales
        self.gestor_atajos = GestorAtajos()
        self.gestor_atajos.registrar(
            self.cfg.atajos.responder,
            lambda: self._on_atajo(modo_repaso=False),
        )
        self.gestor_atajos.registrar(
            self.cfg.atajos.repasar,
            lambda: self._on_atajo(modo_repaso=True),
        )
        self.gestor_atajos.registrar(
            self.cfg.atajos.captura,
            self._on_atajo_captura,
        )
        self.gestor_atajos.iniciar()

        # Bandeja
        self.bandeja = Bandeja(
            on_reindexar=self._reindexar,
            on_salir=self._salir,
            on_ver_uso=self._ver_uso_hoy,
        )
        self.bandeja.iniciar()

        logger.info("Chuleta iniciada correctamente.")

        # Bucle principal de tkinter
        self._root.mainloop()

    def _on_atajo_captura(self):
        """Callback cuando se pulsa Ctrl+Alt+S para capturar recuadro de pantalla."""
        self.selector_recuadro.iniciar_seleccion(self._procesar_region_capturada)

    def _procesar_region_capturada(self, region: Optional[tuple[int, int, int, int]]):
        """Procesa el recuadro seleccionado por el usuario.

        Pipeline de 3 fases para captura visual genérica:
          1. Describir: Gemini Vision transcribe/describe el contenido de la imagen.
          2. Buscar: Usar esa descripción como consulta para recuperar fragmentos relevantes.
          3. Responder: Enviar imagen + fragmentos + prompt para generar la respuesta final.
        """
        if not region:
            return

        def _tarea():
            try:
                self.cuadro.mostrar_espera()
                from .captura import capturar_pantalla_region
                img = capturar_pantalla_region(region)
                if not img:
                    self.cuadro.mostrar("Error al capturar la pantalla")
                    return

                # Convertir a bytes JPEG para Gemini
                import io
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                jpeg_bytes = buf.getvalue()

                from google.genai import types
                from .limites import ejecutar_con_reintentos

                part_imagen = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")

                # ── Fase 1: Describir el contenido de la imagen ──
                # Pedir a Gemini Vision que transcriba/describa brevemente lo que ve
                # (texto, preguntas, opciones, etiquetas, diagramas, etc.)
                prompt_describir = (
                    "Transcribe y describe brevemente el contenido de esta imagen. "
                    "Extrae todo el texto visible, preguntas, opciones de respuesta, "
                    "etiquetas de diagramas y cualquier elemento relevante. "
                    "Sé conciso, solo enumera lo que ves sin responder preguntas."
                )

                def _llamar_describir():
                    return self.client.models.generate_content(
                        model=self.cfg.modelos.chat,
                        contents=[part_imagen, prompt_describir],
                        config=types.GenerateContentConfig(
                            temperature=0.1,
                            max_output_tokens=300,
                        ),
                    )

                resp_descripcion = ejecutar_con_reintentos(
                    _llamar_describir, tipo="chat", cfg=self.cfg,
                )
                descripcion_imagen = (resp_descripcion.text or "").strip()

                if not descripcion_imagen:
                    logger.warning("Gemini no pudo describir la imagen capturada")
                    self.cuadro.mostrar("No se pudo leer el contenido de la imagen.")
                    return

                logger.info(f"Descripción de captura: {descripcion_imagen[:120]}...")

                # ── Fase 2: Buscar fragmentos relevantes usando la descripción ──
                resultado_busqueda = buscar(
                    self.indice,
                    descripcion_imagen,
                    self.cfg,
                    self.client,
                )

                # ── Fase 3: Generar respuesta con imagen + fragmentos ──
                prompt_vision = (
                    "Analiza esta captura de pantalla de un test o ejercicio educativo. "
                    "1. Lee el texto, pregunta, opciones o esquemas que aparecen en la imagen. "
                    "2. Responde o identifica la opción correcta basándote en los "
                    "fragmentos de apuntes proporcionados. "
                    "Si son esquemas o diagramas, indica claramente qué representan "
                    "o cuál es la solución."
                )

                respuesta = generar_respuesta(
                    self.client,
                    prompt_vision,
                    resultado_busqueda.fragmentos,
                    self.cfg,
                    imagen=part_imagen,
                )

                if respuesta and (respuesta.encontrada or respuesta.respuesta):
                    fuente = "Captura / Apuntes"
                    if 1 <= respuesta.fragmento <= len(resultado_busqueda.fragmentos):
                        frag = resultado_busqueda.fragmentos[respuesta.fragmento - 1]
                        fuente = frag.archivo
                        if frag.pagina:
                            fuente += f", p. {frag.pagina}"
                    self.cuadro.mostrar(respuesta.respuesta, fuente)
                else:
                    self.cuadro.mostrar("No se pudo identificar con certeza.")

            except CuotaDiariaAgotadaError:
                self.cuadro.mostrar("Límite diario agotado hasta mañana.")
            except LimiteMinutoError:
                self.cuadro.mostrar("Límite de uso: espera un momento")
            except Exception as e:
                error_str = str(e).lower()
                if "connection" in error_str or "network" in error_str:
                    self.cuadro.mostrar("Sin conexión")
                elif "quota" in error_str or "429" in error_str:
                    self.cuadro.mostrar("Límite de uso: espera un momento")
                else:
                    logger.error(f"Error procesando captura de pantalla: {e}", exc_info=True)
                    self.cuadro.mostrar("Error procesando imagen")

        threading.Thread(target=_tarea, daemon=True).start()

    def _ver_uso_hoy(self):
        """Muestra estadísticas de uso diario de la API en el cuadro flotante."""
        uso = contador_uso.obtener()
        alerta = contador_uso.alerta_cuota_baja()
        extra_alerta = f"\n\n{alerta}" if alerta else ""
        msg = (
            f"Uso de hoy (Gemini Free Tier):\n\n"
            f"• Chat: {uso['chat_usadas']} / {uso['chat_limite']} peticiones ({uso['chat_restantes']} restantes)\n"
            f"• Embeddings: {uso['embeddings_usadas']} / {uso['embeddings_limite']} peticiones ({uso['embeddings_restantes']} restantes)\n"
            f"• Ritmo max: {self.cfg.limites.chat_rpm} chat/min | {self.cfg.limites.embed_rpm} embed/min"
            f"{extra_alerta}"
        )
        self.cuadro.mostrar(msg, duracion_seg=8.0)

    def _on_atajo(self, modo_repaso: bool):
        """Callback cuando se pulsa un atajo global."""
        # Ejecutar en hilo separado para no bloquear
        threading.Thread(
            target=self._procesar_atajo,
            args=(modo_repaso,),
            daemon=True,
        ).start()

    def _procesar_atajo(self, modo_repaso: bool):
        """Procesa la selección capturada."""
        try:
            # Capturar selección PRIMERO mientras la app activa mantiene el foco
            texto = capturar_seleccion()
            if not texto:
                self.cuadro.mostrar("Selecciona una pregunta primero.")
                return

            # Mostrar indicador de espera tras capturar la selección
            self.cuadro.mostrar_espera()

            # Limitar texto
            if len(texto) > 8000:
                texto = texto[:8000]

            # Verificar clave
            if not self.client:
                self.cuadro.mostrar("Falta la clave de Gemini")
                return

            modo = "repaso" if modo_repaso else "responder"

            # Modo test
            if not modo_repaso and es_modo_test(texto, self.cfg):
                self._procesar_test(texto)
                return

            # Buscar en caché
            cached = self.cache.obtener(texto, modo)
            if cached:
                self.cuadro.mostrar(
                    cached["texto"],
                    cached.get("fuente", ""),
                )
                return

            # Pipeline completo
            resultado = self._pipeline(texto, modo_repaso)

            alerta = contador_uso.alerta_cuota_baja()
            extra = f"\n\n[{alerta}]" if alerta else ""

            if resultado["ok"]:
                self.cuadro.mostrar(resultado["texto"] + extra, resultado.get("fuente", ""))
                self.cache.guardar(texto, modo, resultado)
            else:
                self.cuadro.mostrar(resultado["texto"] + extra)

        except CuotaDiariaAgotadaError:
            self.cuadro.mostrar("Límite diario agotado hasta mañana.")
        except LimiteMinutoError:
            self.cuadro.mostrar("Límite de uso: espera un momento")
        except ValueError as e:
            self.cuadro.mostrar(str(e))
        except Exception as e:
            error_str = str(e).lower()
            if "connection" in error_str or "network" in error_str:
                self.cuadro.mostrar("Sin conexión")
            elif "quota" in error_str or "rate" in error_str or "429" in error_str:
                self.cuadro.mostrar("Límite de uso: espera un momento")
            else:
                logger.error(f"Error procesando: {e}", exc_info=True)
                self.cuadro.mostrar("Error inesperado")

    def _pipeline(self, texto: str, modo_repaso: bool) -> dict:
        """Ejecuta el pipeline completo: recuperación → generación → verificación."""
        import time

        # Recuperación (reutilizar fragmentos en modo repaso si se consultó hace poco)
        resultado_busqueda = None
        if modo_repaso and texto in self._cache_fragmentos:
            ts, res_cached = self._cache_fragmentos[texto]
            if time.time() - ts < 600:
                logger.info("Modo repaso: reutilizando fragmentos recuperados recientemente")
                resultado_busqueda = res_cached

        if resultado_busqueda is None:
            resultado_busqueda = buscar(
                self.indice, texto, self.cfg, self.client,
            )
            self._cache_fragmentos[texto] = (time.time(), resultado_busqueda)

        if not resultado_busqueda.pasa_umbral:
            return {
                "ok": False,
                "texto": "No está en los documentos.",
            }

        if not resultado_busqueda.fragmentos:
            return {
                "ok": False,
                "texto": "No está en los documentos.",
            }

        # Generación
        respuesta = generar_respuesta(
            self.client,
            texto,
            resultado_busqueda.fragmentos,
            self.cfg,
            modo_repaso=modo_repaso,
        )

        if not respuesta:
            return {"ok": False, "texto": "No está en los documentos."}

        # Verificación
        es_valida, razon = verificar(
            respuesta,
            resultado_busqueda.fragmentos,
            self.cfg,
            texto_pregunta=texto,
        )

        if not es_valida:
            # Reintentar UNA vez si falló por cita no literal o JSON inválido
            if "cita literal" in razon.lower() or "json" in razon.lower():
                logger.info(f"Reintentando (razón: {razon})")
                respuesta = generar_respuesta(
                    self.client,
                    texto,
                    resultado_busqueda.fragmentos,
                    self.cfg,
                    modo_repaso=modo_repaso,
                    es_reintento=True,
                )

                if respuesta:
                    es_valida, razon = verificar(
                        respuesta,
                        resultado_busqueda.fragmentos,
                        self.cfg,
                        texto_pregunta=texto,
                    )

            if not es_valida:
                logger.info(f"Verificador rechazó: {razon}")
                return {"ok": False, "texto": "No está en los documentos."}

        # Construir fuente
        idx_frag = respuesta.fragmento - 1
        if 0 <= idx_frag < len(resultado_busqueda.fragmentos):
            frag = resultado_busqueda.fragmentos[idx_frag]
            fuente = frag.archivo
            if frag.pagina is not None:
                fuente += f", p. {frag.pagina}"
            elif frag.seccion:
                fuente += f", {frag.seccion}"
        else:
            fuente = ""

        return {
            "ok": True,
            "texto": respuesta.respuesta,
            "opcion": respuesta.opcion,
            "fuente": fuente,
            "respuesta": respuesta.respuesta,
        }

    def _procesar_test(self, texto: str):
        """Procesa un test de varias preguntas."""
        preguntas = separar_preguntas(texto, self.client, self.cfg)

        if not preguntas:
            # Fallback: tratar como pregunta única
            resultado = self._pipeline(texto, False)
            if resultado["ok"]:
                self.cuadro.mostrar(resultado["texto"], resultado.get("fuente", ""))
            else:
                self.cuadro.mostrar(resultado["texto"])
            return

        def pipeline_fn(texto_pregunta: str, es_repaso: bool) -> dict:
            return self._pipeline(texto_pregunta, es_repaso)

        resultados = procesar_test(
            preguntas,
            pipeline_fn=pipeline_fn,
            cfg=self.cfg,
            indice=self.indice,
            client=self.client,
        )
        texto_resultado = formatear_resultados_test(resultados)

        alerta = contador_uso.alerta_cuota_baja()
        if alerta:
            texto_resultado += f"\n\n[{alerta}]"

        # Duración: segundos_por_pregunta × nº de preguntas
        duracion = min(
            self.cfg.test.segundos_por_pregunta * len(preguntas),
            self.cfg.test.segundos_max_test,
        )

        self.cuadro.mostrar(texto_resultado, duracion_seg=duracion)

    def _reindexar(self):
        """Reindexa los documentos (desde la bandeja)."""
        def _hacer():
            try:
                logger.info("Reindexando documentos...")
                self.cuadro.mostrar("Reindexando…", duracion_seg=60)
                stats = self.indice.indexar(forzar=True)
                self.cache.actualizar_version(self.indice.version)
                msg = (
                    f"Reindexado: {stats['fragmentos_total']} fragmentos "
                    f"de {stats['archivos_total']} archivos"
                )
                logger.info(msg)
                self.cuadro.mostrar(msg)
            except Exception as e:
                logger.error(f"Error reindexando: {e}")
                self.cuadro.mostrar(f"Error al reindexar: {e}")

        threading.Thread(target=_hacer, daemon=True).start()

    def _salir(self):
        """Cierra la aplicación."""
        logger.info("Cerrando Chuleta...")
        if self.gestor_atajos:
            self.gestor_atajos.detener()
        if self.cuadro:
            self.cuadro.cerrar()
        if self._root:
            self._root.after(0, self._root.quit)


def ejecutar_pipeline_cli(
    texto: str,
    cfg: Config,
    client,
    indice: Indice,
    modo_repaso: bool = False,
) -> dict:
    """Ejecuta el pipeline completo y devuelve resultados detallados para CLI."""
    resultado_busqueda = buscar(indice, texto, cfg, client)

    info = {
        "fragmentos": [],
        "pasa_umbral": resultado_busqueda.pasa_umbral,
        "json_modelo": None,
        "verificador": None,
        "respuesta_final": None,
    }

    for i, frag in enumerate(resultado_busqueda.fragmentos):
        info["fragmentos"].append({
            "archivo": frag.archivo,
            "pagina": frag.pagina,
            "seccion": frag.seccion,
            "score_semantico": resultado_busqueda.scores_semanticos[i] if i < len(resultado_busqueda.scores_semanticos) else 0,
            "score_lexico": resultado_busqueda.scores_lexicos[i] if i < len(resultado_busqueda.scores_lexicos) else 0,
            "score_fusionado": resultado_busqueda.scores_fusionados[i] if i < len(resultado_busqueda.scores_fusionados) else 0,
            "texto": frag.texto[:200] + "..." if len(frag.texto) > 200 else frag.texto,
        })

    if not resultado_busqueda.pasa_umbral:
        info["respuesta_final"] = "No está en los documentos."
        return info

    if not resultado_busqueda.fragmentos:
        info["respuesta_final"] = "No está en los documentos."
        return info

    # Generación
    respuesta = generar_respuesta(
        client, texto, resultado_busqueda.fragmentos, cfg,
        modo_repaso=modo_repaso,
    )

    if respuesta:
        info["json_modelo"] = respuesta.json_crudo

        es_valida, razon = verificar(
            respuesta, resultado_busqueda.fragmentos, cfg,
            texto_pregunta=texto,
        )
        info["verificador"] = {"valida": es_valida, "razon": razon}

        if not es_valida and ("cita literal" in razon.lower() or "json" in razon.lower()):
            respuesta = generar_respuesta(
                client, texto, resultado_busqueda.fragmentos, cfg,
                modo_repaso=modo_repaso, es_reintento=True,
            )
            if respuesta:
                info["json_modelo"] = respuesta.json_crudo
                es_valida, razon = verificar(
                    respuesta, resultado_busqueda.fragmentos, cfg,
                    texto_pregunta=texto,
                )
                info["verificador"] = {"valida": es_valida, "razon": razon}

        if es_valida:
            idx = respuesta.fragmento - 1
            fuente = ""
            if 0 <= idx < len(resultado_busqueda.fragmentos):
                frag = resultado_busqueda.fragmentos[idx]
                fuente = frag.archivo
                if frag.pagina is not None:
                    fuente += f", p. {frag.pagina}"
                elif frag.seccion:
                    fuente += f", {frag.seccion}"
            info["respuesta_final"] = f"{respuesta.respuesta} [{fuente}]"
        else:
            info["respuesta_final"] = "No está en los documentos."
    else:
        info["respuesta_final"] = "No está en los documentos."

    return info
