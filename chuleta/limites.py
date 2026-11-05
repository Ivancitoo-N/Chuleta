"""Control de ritmo (rate limiting), cuota diaria y reintentos para Gemini Free Tier."""

from __future__ import annotations

import datetime
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import DIR_INDICE, Config

logger = logging.getLogger("chuleta.limites")

ARCHIVO_USO = DIR_INDICE / "uso_diario.json"


def extraer_segundos_espera(e: Exception) -> Optional[float]:
    """Intenta extraer el tiempo de espera sugerido por la API de Google (ej. retryDelay: '39s')."""
    texto = str(e)
    match = re.search(r"retrydelay['\":\s]+(\d+(?:\.\d+)?)s?", texto, re.IGNORECASE)
    if not match:
        match = re.search(r"retry in (\d+(?:\.\d+)?)\s*s?", texto, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


class CuotaDiariaAgotadaError(Exception):
    """Se lanza cuando se alcanza el tope diario de la API gratuita."""
    pass


class LimiteMinutoError(Exception):
    """Se lanza cuando se agotan los reintentos tras límite por minuto."""
    pass


class ContadorUsoDiario:
    """Registra y persiste el uso diario de la API de Gemini."""

    def __init__(self, ruta_archivo: Optional[Path] = None):
        self.ruta = ruta_archivo or ARCHIVO_USO
        self._lock = threading.Lock()
        self.limite_chat_diario = 500
        self.limite_embed_diario = 1000

    def _hoy_str(self) -> str:
        return datetime.date.today().isoformat()

    def _cargar(self) -> Dict[str, Any]:
        hoy = self._hoy_str()
        if self.ruta.exists():
            try:
                with open(self.ruta, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                if datos.get("fecha") == hoy:
                    return datos
            except Exception as e:
                logger.warning(f"No se pudo leer {self.ruta}, reiniciando: {e}")

        # Reiniciar para el nuevo día
        return {
            "fecha": hoy,
            "chat_usadas": 0,
            "embeddings_usadas": 0,
            "chat_limite": self.limite_chat_diario,
            "embeddings_limite": self.limite_embed_diario,
        }

    def _guardar(self, datos: Dict[str, Any]):
        try:
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ruta, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error guardando contador diario: {e}")

    def registrar(self, tipo: str, cantidad: int = 1):
        """Registra una o más peticiones consumidas."""
        with self._lock:
            datos = self._cargar()
            if tipo == "chat":
                datos["chat_usadas"] = datos.get("chat_usadas", 0) + cantidad
            elif tipo == "embeddings":
                datos["embeddings_usadas"] = datos.get("embeddings_usadas", 0) + cantidad
            self._guardar(datos)

    def obtener(self) -> Dict[str, Any]:
        """Devuelve las estadísticas completas de uso de hoy."""
        with self._lock:
            datos = self._cargar()
            chat_usadas = datos.get("chat_usadas", 0)
            emb_usadas = datos.get("embeddings_usadas", 0)
            chat_rest = max(0, self.limite_chat_diario - chat_usadas)
            emb_rest = max(0, self.limite_embed_diario - emb_usadas)
            return {
                "fecha": datos.get("fecha", self._hoy_str()),
                "chat_usadas": chat_usadas,
                "chat_limite": self.limite_chat_diario,
                "chat_restantes": chat_rest,
                "embeddings_usadas": emb_usadas,
                "embeddings_limite": self.limite_embed_diario,
                "embeddings_restantes": emb_rest,
            }

    def es_limite_diario_agotado(self, tipo: str) -> bool:
        """Comprueba si se ha agotado la cuota de hoy."""
        uso = self.obtener()
        if tipo == "chat":
            return uso["chat_restantes"] <= 0
        elif tipo == "embeddings":
            return uso["embeddings_restantes"] <= 0
        return False

    def alerta_cuota_baja(self) -> Optional[str]:
        """Devuelve un aviso si queda menos del 10 % de cuota diaria."""
        uso = self.obtener()
        avisos = []
        # 10% de 500 = 50
        if uso["chat_restantes"] < 50:
            avisos.append(f"Chat: {uso['chat_restantes']}/{self.limite_chat_diario} restantes hoy")
        # 10% de 1000 = 100
        if uso["embeddings_restantes"] < 100:
            avisos.append(f"Embeddings: {uso['embeddings_restantes']}/{self.limite_embed_diario} restantes hoy")

        if avisos:
            return "⚠️ Te queda menos del 10% de cuota diaria de Gemini (" + ", ".join(avisos) + ")"
        return None


class LimitadorRitmo:
    """Limitador de peticiones/minuto y tokens/minuto por ventana deslizante (60s)."""

    def __init__(self, chat_rpm: int = 12, embed_rpm: int = 80, max_tpm: int = 20000):
        self.chat_rpm = chat_rpm
        self.embed_rpm = embed_rpm
        self.max_tpm = max_tpm

        self._lock = threading.Lock()
        self._tiempos_chat: List[float] = []
        self._tiempos_embed: List[Tuple[float, int]] = []  # (timestamp, tokens)

    def actualizar_config(self, cfg: Config):
        with self._lock:
            self.chat_rpm = cfg.limites.chat_rpm
            self.embed_rpm = cfg.limites.embed_rpm
            self.max_tpm = cfg.limites.max_tokens_por_minuto

    def adquirir(self, tipo: str, tokens_estimados: int = 0):
        """Bloquea y espera el tiempo necesario si se excede la ventana deslizante."""
        while True:
            with self._lock:
                ahora = time.time()
                ventana_inicio = ahora - 60.0

                if tipo == "chat":
                    # Limpiar tiempos viejos
                    self._tiempos_chat = [t for t in self._tiempos_chat if t > ventana_inicio]
                    if len(self._tiempos_chat) < self.chat_rpm:
                        self._tiempos_chat.append(ahora)
                        return
                    # Esperar a que el más antiguo salga de la ventana
                    mas_antiguo = self._tiempos_chat[0]
                    tiempo_espera = max(0.1, (mas_antiguo + 60.0) - ahora + 0.05)

                elif tipo == "embeddings":
                    # Limpiar tiempos viejos
                    self._tiempos_embed = [(t, tok) for t, tok in self._tiempos_embed if t > ventana_inicio]
                    tokens_actuales = sum(tok for _, tok in self._tiempos_embed)

                    rpm_ok = len(self._tiempos_embed) < self.embed_rpm
                    tpm_ok = (tokens_actuales + tokens_estimados) <= self.max_tpm or not self._tiempos_embed

                    if rpm_ok and tpm_ok:
                        self._tiempos_embed.append((ahora, tokens_estimados))
                        return

                    mas_antiguo = self._tiempos_embed[0][0]
                    tiempo_espera = max(0.1, (mas_antiguo + 60.0) - ahora + 0.05)
                else:
                    return

            logger.info(f"Límite {tipo} alcanzado. Esperando {tiempo_espera:.1f}s...")
            time.sleep(tiempo_espera)


# Instancias globales singleton
contador_uso = ContadorUsoDiario()
limitador_ritmo = LimitadorRitmo()


def ejecutar_con_reintentos(
    fn: Callable[[], Any],
    tipo: str,
    tokens_estimados: int = 0,
    cfg: Optional[Config] = None,
) -> Any:
    """Ejecuta una llamada a Gemini respetando cuota diaria, RPM y reintentos exponenciales."""
    if cfg:
        limitador_ritmo.actualizar_config(cfg)

    # 1. Verificar si el límite diario ya se agotó
    if contador_uso.es_limite_diario_agotado(tipo):
        raise CuotaDiariaAgotadaError("Límite diario agotado hasta mañana.")

    # 2. Adquirir permiso del limitador de ritmo por minuto
    limitador_ritmo.adquirir(tipo, tokens_estimados=tokens_estimados)

    # 3. Intentos con espera exponencial: 2s, 4s, 8s (máximo 3 reintentos)
    tiempos_espera = [2.0, 4.0, 8.0]
    ultimo_error = None

    for intento in range(len(tiempos_espera) + 1):
        try:
            resultado = fn()
            contador_uso.registrar(tipo)
            return resultado
        except Exception as e:
            ultimo_error = e
            err_str = str(e).lower()

            # Error de autenticación / API Key no se reintenta
            if "api key" in err_str or "unregistered" in err_str:
                raise ValueError("Clave de Gemini inválida") from e

            # Distinguir cuota diaria de cuota por minuto
            es_cuota = "quota" in err_str or "429" in err_str or "resource_exhausted" in err_str or "rate" in err_str
            espera_api = extraer_segundos_espera(e)

            es_diario = (
                "day" in err_str
                or "daily" in err_str
                or "per-day" in err_str
                or contador_uso.es_limite_diario_agotado(tipo)
                or (espera_api is not None and espera_api > 180)
            )

            if es_cuota and es_diario:
                logger.error(f"Cuota diaria agotada para {tipo}: {e}")
                raise CuotaDiariaAgotadaError("Límite diario agotado hasta mañana.") from e

            if es_cuota:
                if intento < len(tiempos_espera):
                    espera = tiempos_espera[intento]
                    if espera_api is not None and espera_api > 0:
                        espera = min(max(espera, espera_api + 0.5), 65.0)
                    logger.warning(
                        f"Límite por minuto ({tipo}). Reintento {intento + 1}/3 esperando {espera:.1f}s: {e}"
                    )
                    time.sleep(espera)
                    continue
                else:
                    logger.error(f"Límite por minuto agotado tras reintentos ({tipo}): {e}")
                    raise LimiteMinutoError("Límite de uso: espera un momento") from e

            # Otros errores no relacionados con límites
            if intento < len(tiempos_espera):
                espera = tiempos_espera[intento]
                logger.warning(f"Error temporal ({tipo}). Reintento en {espera}s: {e}")
                time.sleep(espera)
            else:
                raise

    if ultimo_error:
        raise ultimo_error
