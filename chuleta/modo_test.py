"""Modo test: detección, separación y procesamiento paralelo de varias preguntas."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Optional, Tuple, Callable

from .config import Config

logger = logging.getLogger("chuleta.modo_test")


@dataclass
class PreguntaTest:
    """Una pregunta individual del test."""
    numero: int
    texto_completo: str
    enunciado: str
    opciones: List[str]  # ["a) texto", "b) texto", ...]


@dataclass
class ResultadoTest:
    """Resultado de una pregunta del test."""
    numero: int
    respuesta: str  # "A", "B", "V", "F", "?"
    fuente: Optional[str] = None


def es_modo_test(texto: str, cfg: Config) -> bool:
    """Detecta si el texto contiene varias preguntas (modo test)."""
    if not cfg.test.activado:
        return False

    # Patrones de numeración
    patrones_numeracion = [
        r"(?:^|\n)\s*\d+[.)]\s",           # 1. o 1)
        r"(?:^|\n)\s*Pregunta\s+\d+",       # Pregunta 1
    ]

    # Contar preguntas numeradas
    for patron in patrones_numeracion:
        matches = re.findall(patron, texto, re.IGNORECASE)
        if len(matches) >= 2:
            return True

    # Múltiples bloques con opciones a/b/c/d
    bloques_opciones = re.findall(
        r"(?:^|\n).*?\n\s*[aA][.)]\s.*?\n\s*[bB][.)]\s",
        texto,
        re.DOTALL,
    )
    if len(bloques_opciones) >= 2:
        return True

    return False


def separar_preguntas_regex(texto: str) -> List[PreguntaTest]:
    """Separa preguntas usando regex cuando la numeración es clara."""
    preguntas: list[PreguntaTest] = []

    # Intentar separar por numeración: "1.", "2)", "Pregunta 3", etc.
    patron = r"(?:^|\n)\s*(?:Pregunta\s+)?(\d+)[.)]\s*"

    # Encontrar todas las posiciones de inicio de pregunta
    matches = list(re.finditer(patron, texto, re.IGNORECASE))

    if len(matches) < 2:
        return preguntas

    for i, match in enumerate(matches):
        numero = int(match.group(1))
        inicio = match.end()

        # El texto de esta pregunta va hasta el inicio de la siguiente
        if i + 1 < len(matches):
            fin = matches[i + 1].start()
        else:
            fin = len(texto)

        texto_pregunta = texto[inicio:fin].strip()
        if not texto_pregunta:
            continue

        # Separar enunciado y opciones
        enunciado, opciones = _extraer_enunciado_opciones(texto_pregunta)

        preguntas.append(PreguntaTest(
            numero=numero,
            texto_completo=texto_pregunta,
            enunciado=enunciado,
            opciones=opciones,
        ))

    return preguntas


def _extraer_enunciado_opciones(texto: str) -> Tuple[str, List[str]]:
    """Separa enunciado de opciones en una pregunta."""
    opciones: list[str] = []

    # Buscar opciones (admite a-z, no solo a-d)
    patron_opcion = r"(?:^|\n)\s*([a-zA-Z])[.)]\s*(.+?)(?=(?:\n\s*[a-zA-Z][.)]\s)|\Z)"
    matches = list(re.finditer(patron_opcion, texto, re.DOTALL))

    if matches:
        # El enunciado es todo lo que está antes de la primera opción
        enunciado = texto[:matches[0].start()].strip()
        for m in matches:
            letra = m.group(1).lower()
            texto_opcion = m.group(2).strip()
            opciones.append(f"{letra}) {texto_opcion}")
    else:
        enunciado = texto
        # Verificar verdadero/falso
        if re.search(r"\b(?:verdadero|falso|V/F|V|F)\b", texto, re.IGNORECASE):
            opciones = ["V", "F"]

    return enunciado, opciones


def separar_preguntas_con_modelo(
    texto: str,
    client,
    cfg: Config,
) -> List[PreguntaTest]:
    """Usa Gemini para separar preguntas cuando el regex no basta."""
    from google.genai import types

    prompt = (
        "Separa las siguientes preguntas de examen. "
        "Devuelve un JSON con una lista de objetos, cada uno con: "
        '"numero" (int), "enunciado" (string), "opciones" (lista de strings como "a) texto").\n\n'
        f"Texto:\n{texto}"
    )

    schema = {
        "type": "object",
        "properties": {
            "preguntas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "numero": {"type": "integer"},
                        "enunciado": {"type": "string"},
                        "opciones": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["numero", "enunciado", "opciones"],
                },
            },
        },
        "required": ["preguntas"],
    }

    try:
        cfg_kwargs = {
            "response_mime_type": "application/json",
            "response_schema": schema,
            "temperature": 0,
            "max_output_tokens": 2048,
        }
        if "lite" not in cfg.modelos.chat.lower():
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

        response = client.models.generate_content(
            model=cfg.modelos.chat,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs),
        )

        datos = json.loads(response.text)
        preguntas = []
        for p in datos.get("preguntas", []):
            texto_completo = p["enunciado"]
            if p.get("opciones"):
                texto_completo += "\n" + "\n".join(p["opciones"])
            preguntas.append(PreguntaTest(
                numero=p["numero"],
                texto_completo=texto_completo,
                enunciado=p["enunciado"],
                opciones=p.get("opciones", []),
            ))
        return preguntas

    except Exception as e:
        logger.error(f"Error separando preguntas con modelo: {e}")
        return []


def separar_preguntas(
    texto: str,
    client=None,
    cfg: Config = None,
) -> List[PreguntaTest]:
    """Separa preguntas: primero con regex, si falla con el modelo."""
    preguntas = separar_preguntas_regex(texto)

    if not preguntas and client and cfg:
        logger.info("Numeración no clara, usando modelo para separar preguntas")
        preguntas = separar_preguntas_con_modelo(texto, client, cfg)

    # Limitar al máximo configurado
    if cfg and len(preguntas) > cfg.test.max_preguntas:
        preguntas = preguntas[:cfg.test.max_preguntas]

    return preguntas


def procesar_test(
    preguntas: List[PreguntaTest],
    pipeline_fn: Optional[Callable[[str, bool], dict]] = None,
    cfg: Optional[Config] = None,
    indice = None,
    client = None,
) -> List[ResultadoTest]:
    """Procesa las preguntas del test en lotes (máximo lote_max por petición).

    Agrupa embeddings y realiza UNA SOLA llamada a Gemini por lote de preguntas.
    Cada pregunta se verifica por separado con sus propios fragmentos.
    """
    if not preguntas:
        return []

    cfg = cfg or Config()

    # Si se pasa índice y cliente, usamos el modo eficiente en lote (1 request por lote)
    if indice is not None and client is not None:
        from .recuperacion import buscar, embeddings_consultas
        from .generacion import generar_respuestas_lote
        from .verificador import verificar

        lote_max = getattr(cfg.test, "lote_max", 15)
        resultados_map: dict[int, ResultadoTest] = {}

        # Dividir en lotes de máximo lote_max
        for i in range(0, len(preguntas), lote_max):
            lote = preguntas[i:i + lote_max]

            # 1. Embeddings agrupados para todas las preguntas del lote (1 llamada)
            textos_lote = [p.texto_completo for p in lote]
            vectores_emb = embeddings_consultas(client, textos_lote, cfg)

            # 2. Recuperación local de fragmentos para cada pregunta
            preguntas_con_frags: List[Tuple[int, str, list]] = []
            frags_por_num: dict[int, list] = {}

            for p, q_emb in zip(lote, vectores_emb):
                recup = buscar(indice, p.texto_completo, cfg, client=client, query_emb=q_emb)
                if recup.pasa_umbral and recup.fragmentos:
                    frags_por_num[p.numero] = recup.fragmentos
                    preguntas_con_frags.append((p.numero, p.texto_completo, recup.fragmentos))
                else:
                    frags_por_num[p.numero] = []

            # 3. Generación en UNA SOLA llamada para todo el lote
            respuestas_modelo = {}
            if preguntas_con_frags:
                try:
                    respuestas_modelo = generar_respuestas_lote(client, preguntas_con_frags, cfg)
                except Exception as e:
                    logger.error(f"Error generando lote de test: {e}")

            # 4. Verificación independiente por pregunta
            for p in lote:
                resp_mod = respuestas_modelo.get(p.numero)
                frags = frags_por_num.get(p.numero, [])

                if not resp_mod or not resp_mod.encontrada or not frags:
                    resultados_map[p.numero] = ResultadoTest(numero=p.numero, respuesta="?")
                    continue

                es_valida, _ = verificar(resp_mod, frags, cfg, texto_pregunta=p.texto_completo)
                if not es_valida:
                    resultados_map[p.numero] = ResultadoTest(numero=p.numero, respuesta="?")
                    continue

                opcion = resp_mod.opcion
                if opcion:
                    opcion = opcion.strip().upper()
                    if opcion in ("VERDADERO", "TRUE"):
                        opcion = "V"
                    elif opcion in ("FALSO", "FALSE"):
                        opcion = "F"
                    # Tomar la letra de la opción si viene como "A)" o "A."
                    if len(opcion) > 1 and opcion[0] in "ABCDEF":
                        opcion = opcion[0]
                    resultados_map[p.numero] = ResultadoTest(numero=p.numero, respuesta=opcion)
                elif resp_mod.respuesta and len(resp_mod.respuesta) < 30:
                    resultados_map[p.numero] = ResultadoTest(numero=p.numero, respuesta=resp_mod.respuesta)
                else:
                    resultados_map[p.numero] = ResultadoTest(numero=p.numero, respuesta="?")

        return [resultados_map.get(p.numero, ResultadoTest(numero=p.numero, respuesta="?")) for p in preguntas]

    # Modo fallback concurrente / unit tests usando pipeline_fn
    if pipeline_fn is None:
        return [ResultadoTest(numero=p.numero, respuesta="?") for p in preguntas]

    resultados: dict[int, ResultadoTest] = {}

    def _procesar_una(pregunta: PreguntaTest) -> ResultadoTest:
        try:
            resultado = pipeline_fn(pregunta.texto_completo, False)
            if not resultado.get("ok", False):
                return ResultadoTest(numero=pregunta.numero, respuesta="?")

            opcion = resultado.get("opcion")
            respuesta_texto = resultado.get("respuesta", "?")

            if opcion:
                opcion = opcion.strip().upper()
                if opcion in ("VERDADERO", "TRUE"):
                    opcion = "V"
                elif opcion in ("FALSO", "FALSE"):
                    opcion = "F"
                return ResultadoTest(numero=pregunta.numero, respuesta=opcion, fuente=resultado.get("fuente"))
            elif respuesta_texto and len(respuesta_texto) < 50:
                return ResultadoTest(numero=pregunta.numero, respuesta=respuesta_texto, fuente=resultado.get("fuente"))
            return ResultadoTest(numero=pregunta.numero, respuesta="?")
        except Exception as e:
            logger.error(f"Error procesando pregunta {pregunta.numero}: {e}")
            return ResultadoTest(numero=pregunta.numero, respuesta="?")

    workers = getattr(cfg.test, "concurrencia", 1) or 1
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_procesar_una, p): p for p in preguntas}
        for future in as_completed(futures):
            res = future.result()
            resultados[res.numero] = res

    return [resultados.get(p.numero, ResultadoTest(numero=p.numero, respuesta="?")) for p in preguntas]


def formatear_resultados_test(resultados: List[ResultadoTest]) -> str:
    """Formatea los resultados del test en formato compacto."""
    partes = []
    for r in resultados:
        partes.append(f"{r.numero}. {r.respuesta}")

    # Agrupar en filas de 10
    filas = []
    for i in range(0, len(partes), 10):
        filas.append("   ".join(partes[i:i + 10]))

    return "\n".join(filas)
