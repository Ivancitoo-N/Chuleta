"""CLI de depuración y punto de entrada."""

from __future__ import annotations

import json
import sys
import io
import os


def _configurar_stdout():
    """Configura stdout para soportar UTF-8 en Windows."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _banner():
    print("=" * 50)
    print("  Chuleta - Herramienta de estudio")
    print("=" * 50)


def cmd_preguntar(texto: str):
    """Ejecuta el pipeline completo en consola."""
    from .config import cargar_config
    from .indexado import Indice
    from .app import ejecutar_pipeline_cli, _crear_cliente

    cfg = cargar_config()
    client = _crear_cliente(cfg)

    if not client:
        print("[X] Falta la clave de Gemini. Configura GEMINI_API_KEY en .env")
        sys.exit(1)

    indice = Indice(cfg, client)
    if not indice.cargar():
        print("Indexando documentos...")
        stats = indice.indexar()
        print(f"  Archivos: {stats['archivos_total']}")
        print(f"  Fragmentos: {stats['fragmentos_total']}")
        for aviso in stats.get("avisos", []):
            print(f"  [!] {aviso}")

    print(f"\nPregunta: {texto}\n")
    print("-" * 50)

    resultado = ejecutar_pipeline_cli(texto, cfg, client, indice)

    # Fragmentos recuperados
    print("\n[Fragmentos recuperados]")
    for i, frag in enumerate(resultado["fragmentos"], 1):
        print(f"  [{i}] {frag['archivo']}", end="")
        if frag.get("pagina"):
            print(f", p. {frag['pagina']}", end="")
        if frag.get("seccion"):
            print(f", {frag['seccion']}", end="")
        print()
        print(f"      Semantico: {frag['score_semantico']:.4f}  "
              f"Lexico: {frag['score_lexico']:.4f}  "
              f"Fusionado: {frag['score_fusionado']:.4f}")
        print(f"      {frag['texto'][:120]}...")

    print(f"\n  Pasa umbral: {'SI' if resultado['pasa_umbral'] else 'NO'}")

    # JSON del modelo
    if resultado.get("json_modelo"):
        print("\n[JSON del modelo]")
        try:
            parsed = json.loads(resultado["json_modelo"])
            print(f"  {json.dumps(parsed, ensure_ascii=False, indent=2)}")
        except Exception:
            print(f"  {resultado['json_modelo'][:500]}")

    # Verificador
    if resultado.get("verificador"):
        v = resultado["verificador"]
        print(f"\n[Verificador] {'PASA' if v['valida'] else 'FALLA'} - {v['razon']}")

    # Respuesta final
    print(f"\n{'=' * 50}")
    print(f"  Respuesta: {resultado['respuesta_final']}")
    print(f"{'=' * 50}")


def cmd_indexar():
    """Reindexa y muestra estadísticas."""
    from .config import cargar_config
    from .indexado import Indice
    from .app import _crear_cliente

    cfg = cargar_config()
    client = _crear_cliente(cfg)

    indice = Indice(cfg, client)
    indice.cargar()

    print("Indexando documentos...")
    stats = indice.indexar(forzar=True)

    print(f"\n[Estadisticas]")
    print(f"  Archivos totales:  {stats['archivos_total']}")
    print(f"  Nuevos:            {stats['nuevos']}")
    print(f"  Modificados:       {stats['modificados']}")
    print(f"  Borrados:          {stats['borrados']}")
    print(f"  Fragmentos:        {stats['fragmentos_total']}")

    if stats.get("avisos"):
        print(f"\n[Avisos]")
        for aviso in stats["avisos"]:
            print(f"  - {aviso}")

    print("\n[OK] Indexado completado.")


def main():
    """Punto de entrada principal."""
    _configurar_stdout()
    args = sys.argv[1:]

    # Soporte para --cwd <ruta>
    if "--cwd" in args:
        idx = args.index("--cwd")
        if idx + 1 < len(args):
            os.chdir(args[idx + 1])
            args = args[:idx] + args[idx + 2 :]
        else:
            args = args[:idx]

    if not args:
        # Modo app (sin consola)
        _banner()
        print("Iniciando en segundo plano...\n")
        from .app import App
        app = App()
        app.iniciar()

    elif args[0] == "preguntar" and len(args) >= 2:
        _banner()
        texto = " ".join(args[1:])
        cmd_preguntar(texto)

    elif args[0] == "indexar":
        _banner()
        cmd_indexar()

    elif args[0] in ("--help", "-h"):
        _banner()
        print("\nUso:")
        print("  python -m chuleta                    Iniciar la app")
        print('  python -m chuleta preguntar "texto"   Pipeline en consola')
        print("  python -m chuleta indexar             Reindexar documentos")
        print("  python -m chuleta --help              Mostrar esta ayuda")

    else:
        print(f"Comando desconocido: {args[0]}")
        print("Usa --help para ver los comandos disponibles.")
        sys.exit(1)
