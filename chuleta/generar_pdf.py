"""Script para generar un PDF de ejemplo para las pruebas."""

from pathlib import Path


def crear_pdf_ejemplo():
    """Crea un PDF con contenido de física básica."""
    ruta = Path(__file__).resolve().parent.parent / "documentos" / "fisica_basica.pdf"
    ruta.parent.mkdir(parents=True, exist_ok=True)

    contenido_p1 = (
        "Las leyes de Newton son los tres principios fundamentales de la mecanica clasica.\n"
        "Primera ley (Ley de inercia): Un cuerpo permanece en reposo o en movimiento "
        "rectilineo uniforme si no actua ninguna fuerza neta sobre el.\n"
        "Segunda ley: La fuerza neta aplicada sobre un cuerpo es proporcional a la "
        "aceleracion que adquiere. Se expresa como F = m x a, donde F es la fuerza "
        "en newtons, m es la masa en kilogramos y a es la aceleracion en m/s2.\n"
        "Tercera ley (Accion y reaccion): Cuando un cuerpo ejerce una fuerza sobre otro, "
        "el segundo ejerce sobre el primero una fuerza igual en magnitud pero de sentido contrario.\n"
        "La energia cinetica de un cuerpo es Ec = 1/2 mv2, donde m es la masa y v la velocidad.\n"
        "La energia potencial gravitatoria es Ep = mgh, donde h es la altura sobre una "
        "referencia y g es la aceleracion de la gravedad (9,8 m/s2 en la superficie terrestre)."
    )

    contenido_p2 = (
        "La termodinamica estudia la relacion entre calor, trabajo y energia.\n"
        "Primera ley de la termodinamica: La energia no se crea ni se destruye, solo se transforma.\n"
        "Segunda ley de la termodinamica: En cualquier proceso termodinamico espontaneo, "
        "la entropia total del universo siempre aumenta. Es imposible construir una "
        "maquina termica que convierta todo el calor en trabajo.\n"
        "La temperatura absoluta se mide en kelvin (K). La relacion con grados Celsius "
        "es: T(K) = T(C) + 273,15. El cero absoluto (0 K = -273,15 C) es la temperatura "
        "mas baja posible.\n"
        "El calor especifico del agua es 4186 J/(kg C), uno de los mas altos entre las "
        "sustancias comunes."
    )

    _escribir_pdf_raw(ruta, [contenido_p1, contenido_p2])
    print(f"PDF creado: {ruta}")


def _escribir_pdf_raw(ruta: Path, paginas: list):
    """Escribe un PDF válido con texto plano, a mano."""
    ruta.parent.mkdir(parents=True, exist_ok=True)

    # Construir objetos PDF
    # Estructura: Catalog -> Pages -> [Page1, Page2, ...]
    # Cada Page apunta a un stream de contenido y a un recurso Font

    # Pre-calcular todos los objetos
    n_paginas = len(paginas)

    # Objetos:
    # 1: Catalog
    # 2: Pages
    # 3: Font
    # Para cada página i (0-based):
    #   4 + i*2: Page
    #   5 + i*2: Stream
    total_objs = 3 + n_paginas * 2

    # Construir streams
    streams = []
    for texto in paginas:
        lineas = texto.split("\n")
        stream_lines = ["BT", "/F1 11 Tf", "1 0 0 1 72 750 Tm", "14 TL"]
        for linea in lineas:
            escaped = linea.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"({escaped}) '")
        stream_lines.append("ET")
        streams.append("\n".join(stream_lines))

    with open(ruta, "wb") as f:
        f.write(b"%PDF-1.4\n")
        offsets = [0] * (total_objs + 1)  # 1-indexed

        # Obj 1: Catalog
        offsets[1] = f.tell()
        f.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

        # Obj 2: Pages
        kids = " ".join(f"{4 + i * 2} 0 R" for i in range(n_paginas))
        offsets[2] = f.tell()
        f.write(f"2 0 obj\n<< /Type /Pages /Kids [{kids}] /Count {n_paginas} >>\nendobj\n".encode())

        # Obj 3: Font
        offsets[3] = f.tell()
        f.write(b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

        # Pages y streams
        for i in range(n_paginas):
            page_num = 4 + i * 2
            stream_num = 5 + i * 2
            stream_content = streams[i]
            stream_bytes = stream_content.encode("latin-1", errors="replace")

            # Page object
            offsets[page_num] = f.tell()
            page_str = (
                f"{page_num} 0 obj\n"
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 595 842] "
                f"/Contents {stream_num} 0 R "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f">>\nendobj\n"
            )
            f.write(page_str.encode())

            # Stream object
            offsets[stream_num] = f.tell()
            f.write(f"{stream_num} 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode())
            f.write(stream_bytes)
            f.write(b"\nendstream\nendobj\n")

        # xref table
        xref_pos = f.tell()
        f.write(b"xref\n")
        f.write(f"0 {total_objs + 1}\n".encode())
        f.write(b"0000000000 65535 f \n")
        for obj_num in range(1, total_objs + 1):
            f.write(f"{offsets[obj_num]:010d} 00000 n \n".encode())

        # trailer
        f.write(f"trailer\n<< /Size {total_objs + 1} /Root 1 0 R >>\n".encode())
        f.write(b"startxref\n")
        f.write(f"{xref_pos}\n".encode())
        f.write(b"%%EOF\n")


if __name__ == "__main__":
    crear_pdf_ejemplo()
