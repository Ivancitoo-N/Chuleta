# Chuleta 📝

Herramienta de escritorio para estudiar. Selecciona una pregunta en cualquier programa, pulsa un atajo y aparece la respuesta extraída de tus documentos.

**Principio rector:** precisión por encima de todo. Solo responde con información verificada de tus documentos. Si no está, dice "No está en los documentos."

---

## ⚡ Descarga e instalación en 1 comando (Copiar y pegar)

Abre tu terminal (**PowerShell** o CMD en Windows) en la carpeta donde quieras tener la app y pega **uno** de estos comandos:

### 🔹 Opción 1: Si tienes Git instalado (Recomendado)
```powershell
git clone https://github.com/Ivancitoo-N/Chuleta.git; cd Chuleta; .\instalar.bat
```
*(En Linux / macOS / Git Bash usa: `git clone https://github.com/Ivancitoo-N/Chuleta.git && cd Chuleta && pip install -r requirements.txt`)*

### 🔹 Opción 2: Sin Git (Descarga directa desde PowerShell en Windows)
Si no tienes Git en tu PC, abre **PowerShell** y pega esta sola línea:
```powershell
Invoke-WebRequest -Uri "https://github.com/Ivancitoo-N/Chuleta/archive/refs/heads/main.zip" -OutFile "Chuleta.zip"; Expand-Archive "Chuleta.zip" -DestinationPath "."; Rename-Item "Chuleta-main" "Chuleta"; Remove-Item "Chuleta.zip"; cd "Chuleta"; .\instalar.bat
```

> **¿Qué hace `instalar.bat` automáticamente?**
> 1. Comprueba tu instalación de Python.
> 2. Crea el entorno virtual e instala todas las dependencias.
> 3. Crea el archivo de claves `.env` listo para usar.
> 4. Te crea el **acceso directo en tu Escritorio** con el icono de Chuleta.

---

## 🚀 Puesta en marcha rápida

### 1. Consigue tu clave de API de Gemini (Gratis)

Gratis en [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

### 2. Configura la clave

Copia `.env.example` a `.env` y pega tu clave:

```
GEMINI_API_KEY=tu_clave_aqui
```

### 3. Instala las dependencias

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Pon tus documentos

Copia tus apuntes (PDF, MD, TXT) a la carpeta `documentos/`. Se admiten subcarpetas.

### 5. Arranca la app de forma cómoda

Tienes varias opciones preparadas:

- **Desde el Escritorio**: Ya tienes un acceso directo **Chuleta** en tu Escritorio con icono propio. Haz doble clic y listo.
- **Con `iniciar.bat`**: Haz doble clic en [`iniciar.bat`](file:///c:/Iv4n/Anti%20Things/Apps/Github/2026/Chuleta/iniciar.bat) en la carpeta del proyecto.
- **Detener la app**: Haz doble clic en [`detener.bat`](file:///c:/Iv4n/Anti%20Things/Apps/Github/2026/Chuleta/detener.bat) o usa el menú del icono en la bandeja del sistema.
- **Arranque automático con Windows**: Ejecuta [`scripts/arranque_activar.bat`](file:///c:/Iv4n/Anti%20Things/Apps/Github/2026/Chuleta/scripts/arranque_activar.bat) para que se inicie sola al encender tu PC.

La app corre en segundo plano: sin ventana ni consola estorbando, dejando su icono en la bandeja del sistema (junto al reloj de Windows).

---

## 🎯 Cómo se usa

### Modo responder (Ctrl+Alt+Q)
1. Selecciona (subraya) una pregunta en cualquier programa
2. Pulsa **Ctrl+Alt+Q**
3. Aparece un cuadro discreto junto al cursor con la respuesta y la fuente
4. Se cierra solo o haz clic para cerrarlo

### Modo repasar (Ctrl+Alt+E)
1. Selecciona un término o concepto
2. Pulsa **Ctrl+Alt+E**
3. Aparece una explicación breve (2-3 frases) basada en tus documentos

### Modo captura de pantalla / esquemas visuales (Ctrl+Alt+S)
1. Pulsa **Ctrl+Alt+S** en cualquier momento
2. La pantalla se oscurecerá ligeramente y el cursor cambiará a una cruz (`+`)
3. Arrastra con el ratón para trazar un recuadro sobre cualquier imagen, dibujo o esquema de **cualquier temática**
4. Chuleta ejecuta un pipeline en 3 fases: primero describe la imagen, luego busca fragmentos relevantes en tus apuntes, y finalmente genera la respuesta combinando ambos
5. Pulsa **Escape** en cualquier momento si quieres cancelar la selección sin capturar nada

### Modo test (automático en una sola llamada)
Cuando seleccionas un bloque con varias preguntas numeradas (1., 2., etc.) con opciones (a, b, c, d... hasta la z), Chuleta detecta el test automáticamente. Para respetar los límites de la API gratuita:
- Recupera los fragmentos de todas las preguntas agrupando sus embeddings en **una sola petición**.
- Envía el test completo (en lotes de hasta 15 preguntas) en **una única llamada** al modelo de chat solicitando un array JSON estructurado.
- Verifica cada respuesta de manera individual y rigurosa contra sus fragmentos fuente.
- Muestra los resultados en formato compacto:

```
1. B   2. A   3. ?   4. D
```

El `?` significa que no encontró la respuesta con certeza o no superó la verificación.

---

## ⚙️ Configuración

Edita `config.toml` (totalmente documentado en español):

| Sección       | Parámetro                | Default               | Descripción |
|---------------|--------------------------|-----------------------|-------------|
| `atajos`      | `responder`              | Ctrl+Alt+Q            | Atajo para responder preguntas |
| `atajos`      | `repasar`                | Ctrl+Alt+E            | Atajo para repasar conceptos |
| `busqueda`    | `top_k`                  | 6                     | Fragmentos a recuperar por búsqueda |
| `busqueda`    | `umbral_semantico`       | 0.55                  | Mínimo de similitud semántica |
| `busqueda`    | `umbral_lexico`          | 0.15                  | Mínimo de relevancia BM25 |
| `modelos`     | `chat`                   | gemini-3.5-flash-lite | Modelo chat (15 RPM / 500 RPD en Free Tier) |
| `modelos`     | `embeddings`             | gemini-embedding-001  | Modelo embeddings (100 RPM / 30.000 TPM) |
| `limites`     | `chat_rpm`               | 12                    | Ventana deslizante de peticiones/min para chat |
| `limites`     | `embed_rpm`              | 80                    | Ventana deslizante de peticiones/min para embeddings |
| `limites`     | `concurrencia`           | 1                     | Llamadas concurrentes simultáneas |
| `limites`     | `max_tokens_por_minuto`  | 20000                 | Margen de seguridad TPM en embeddings |
| `verificacion`| `evidencia_min_chars`    | 15                    | Mínimo de caracteres en la evidencia literal |
| `verificacion`| `verificacion_modelo`    | false                 | Desactivado para ahorrar llamadas al modelo |
| `cuadro`      | `segundos_min`           | 3                     | Tiempo mínimo de visualización del cuadro |
| `cuadro`      | `opacidad`               | 0.93                  | Transparencia del cuadro emergente |
| `test`        | `lote_max`               | 15                    | Preguntas máximas por lote en modo test |

---

## 🔧 CLI de depuración

### Preguntar en consola (pipeline completo)

```bash
python -m chuleta preguntar "¿Quién inventó el transistor?"
```

Muestra: fragmentos recuperados con puntuaciones, JSON del modelo, resultado del verificador y respuesta final.

### Reindexar

```bash
python -m chuleta indexar
```

Muestra estadísticas: archivos, fragmentos, avisos.

---

## 📏 Calibrar umbrales

Los umbrales `umbral_semantico` y `umbral_lexico` determinan cuándo se descarta una búsqueda como "no encontrada". Para calibrarlos:

1. Prepara preguntas de prueba (unas que sí estén en tus documentos y otras que no)
2. Ejecuta cada una con el CLI:
   ```bash
   python -m chuleta preguntar "pregunta de prueba"
   ```
3. Observa las puntuaciones semántica y léxica de los fragmentos recuperados
4. Ajusta los umbrales en `config.toml`:
   - Si da "No está en los documentos" con preguntas que sí están: **baja** los umbrales
   - Si inventa respuestas a preguntas que no están: **sube** los umbrales
5. Repite hasta encontrar el equilibrio

---

## 📁 Documentos soportados

| Formato | Extracción |
|---------|-----------|
| **PDF** | Texto por página (no soporta escaneados sin OCR) |
| **Markdown** | Por secciones (encabezados #) |
| **TXT** | Por párrafos |

- Se admiten subcarpetas dentro de `documentos/`
- Los archivos ocultos (que empiezan con `.`) se ignoran
- El indexado es incremental: solo reprocesa archivos nuevos o modificados

---

## 🔒 Permisos por sistema operativo

### Windows
- No requiere permisos especiales
- Los atajos globales funcionan directamente

### macOS
- Requiere permisos de **Accesibilidad** (Preferencias del Sistema → Seguridad y Privacidad → Accesibilidad)
- Atajos por defecto: **Cmd+Option+Q** y **Cmd+Option+E**
- Ajusta los atajos en `config.toml` si hay conflicto

### Linux
- Funciona mejor con **X11**
- **Wayland** tiene limitaciones con atajos globales y simulación de teclas
- Si tu sesión es Wayland, considera cambiar a X11 o usa `XDG_SESSION_TYPE=x11`

---

## 🚀 Arranque automático

### Activar
```bash
# Windows
scripts\arranque_activar.bat

# macOS (próximamente)
# Linux (próximamente)
```

### Desactivar
```bash
# Windows
scripts\arranque_desactivar.bat
```

---

## 🛠️ Estructura del proyecto

```
Chuleta/
├── chuleta/              # Paquete principal
│   ├── __init__.py
│   ├── __main__.py       # Punto de entrada
│   ├── config.py         # Carga de configuración
│   ├── limites.py        # Rate limiter deslizante, cuota diaria y reintentos
│   ├── extraccion.py     # Extracción PDF/MD/TXT + troceado
│   ├── indexado.py       # Embeddings + reindexado incremental con progreso
│   ├── recuperacion.py   # BM25 + semántica + RRF + embeddings agrupados
│   ├── generacion.py     # Gemini con salida JSON estructurada y llamadas en lote
│   ├── verificador.py    # Verificación de citas por código
│   ├── modo_test.py      # Detección y procesamiento de tests en 1 sola llamada
│   ├── cuadro.py         # Overlay tkinter
│   ├── captura.py        # Atajos globales + portapapeles
│   ├── bandeja.py        # Icono de bandeja del sistema con "Ver uso de hoy"
│   ├── app.py            # Orquestador principal y caché de fragmentos
│   └── cli.py            # CLI de depuración
├── tests/                # Suite de pruebas unitarias (70 tests)
├── documentos/           # Tus apuntes van aquí
├── scripts/              # Scripts de arranque y acceso directo
├── config.toml           # Configuración
├── .env                  # Tu clave de API (no se sube a git)
├── .env.example          # Plantilla de .env
├── requirements.txt      # Dependencias
├── instalar.bat          # Instalador automático en 1 clic
├── iniciar.bat           # Iniciar Chuleta en segundo plano
├── detener.bat           # Detener la aplicación
└── README.md             # Este archivo
```

---

## 📊 Control de Cuota y Uso Diario

Chuleta está adaptada a las restricciones del nivel gratuito de Google Gemini (`gemini-3.5-flash-lite` y `gemini-embedding-001`):

- **Ver uso de hoy:** Haz clic derecho en el icono de Chuleta en la bandeja del sistema (junto al reloj) y pulsa **"Ver uso de hoy"**. Te mostrará una ventana con el número de consultas de chat y embeddings realizadas hoy vs el tope diario permitido.
- **Ventana deslizante por minuto:** Garantiza que nunca se supere el límite de RPM / TPM evitando errores `429 Too Many Requests`.
- **Reintentos inteligentes:** Si la API devuelve un límite temporal, Chuleta lee el tiempo sugerido por Google (`retryDelay`) o aplica espera exponencial (2s, 4s, 8s).
- **Alerta de cuota baja:** Si te queda menos del 10% de tu cuota diaria, recibirás una notificación de aviso.

---

## ❓ Solución de problemas

| Problema | Causa / Solución |
|----------|-------------------|
| "Falta la clave de Gemini" | Configura `GEMINI_API_KEY` en `.env` |
| "Sin conexión" | Verifica tu conexión a internet |
| "Límite de uso: espera un momento" | Has alcanzado el límite por minuto. Chuleta reintentará automáticamente o espera unos segundos |
| "Límite diario agotado hasta mañana" | Has llegado al tope diario de la API gratuita (500 chat / 1000 embeddings). Se reseteará a medianoche UTC |
| "No está en los documentos" en todo | Baja `umbral_semantico` y `umbral_lexico` en `config.toml` |
| PDF escaneado no se indexa | Chuleta no soporta OCR. Usa PDFs con texto seleccionable |
| Atajo no funciona | Verifica permisos (macOS: Accesibilidad) y que no haya conflicto con otro programa |

