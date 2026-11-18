# Ac2ality Digest

Digest de noticias para la redacción de Ac2ality. Revisa 72 fuentes, se queda con lo publicado en las últimas 12 horas, lo clasifica por categorías, puntúa la relevancia y marca las noticias sensibles.

Funciona en tres sitios con la misma interfaz:

| Dispositivo | Formato | Cómo se actualizan las noticias |
|---|---|---|
| **Windows** | Carpeta `Ac2ality Digest` con `Ac2ality Digest.exe` | Al momento, con el botón **Actualizar** y el progreso en pantalla |
| **Mac** | `Ac2ality Digest.app` | Igual que en Windows |
| **iPhone / iPad** | App web instalable (PWA) | Automáticamente varias veces al día; **Actualizar** trae la última versión |

Ya no hay que instalar Python, abrir una terminal ni dejar una ventana negra abierta. La app sustituye al antiguo `actualizar_y_abrir.bat`, que se puede borrar.

---

## Instalación

### Windows
1. Descarga `Ac2ality-Digest-Windows.zip` desde la pestaña **Releases** (o **Actions → Compilar apps de escritorio → Artifacts**).
2. Descomprímelo donde quieras (por ejemplo en *Documentos*), abre la carpeta **Ac2ality Digest** y haz doble clic en **Ac2ality Digest.exe**. Con la app abierta, clic derecho en su icono de la barra de tareas → **Anclar**.
3. La primera vez Windows puede mostrar *"Windows protegió su PC"*: pulsa **Más información → Ejecutar de todas formas** (pasa con cualquier app sin firma digital de pago).

### Mac
1. Descarga `Ac2ality-Digest-macOS-AppleSilicon.zip` (Mac con chip M1/M2/M3/M4) o `…-macOS-Intel.zip`.
2. Descomprime y arrastra **Ac2ality Digest** a **Aplicaciones**.
3. La primera vez: clic derecho sobre la app → **Abrir** → **Abrir**. Después se abre con doble clic normal.

### iPhone / iPad
1. Abre en **Safari** la dirección de GitHub Pages del repositorio (por ejemplo `https://<usuario>.github.io/streaming-digest/`).
2. Pulsa **Compartir** → **Añadir a pantalla de inicio**.
3. Tendrás el icono de ac2ality; se abre a pantalla completa y guarda la última versión para leerla sin conexión.

> Para que exista esa dirección hay que activar Pages una vez: en GitHub, **Settings → Pages → Source: GitHub Actions**. Si el repositorio es privado, GitHub Pages necesita un plan de pago de GitHub.

---

## Uso

- **Actualizar** (arriba a la derecha): en el ordenador abre un panel que muestra cada fuente consultándose en directo, cuántas noticias van saliendo y en qué fase está (descargar → clasificar → listo). Puedes pulsar *Seguir leyendo mientras tanto* y queda una barra fina de progreso en la cabecera. Si abres la app y las noticias tienen más de 2 horas, se actualizan solas.
- **Categorías**: pestañas de colores con el número de noticias.
- **Filtros**: búsqueda, sensibles sí/no, orden (relevancia, fecha, fuente) y fuente concreta. Vista en tarjetas o en lista compacta.
- **Nuevo**: las noticias que no estaban en la actualización anterior llevan la etiqueta NUEVO.
- **Seleccionar**: toca el círculo de una tarjeta. Abajo aparecen **Copiar**, **Guardar**, **Markdown** y **JSON**. En el ordenador los archivos se guardan en *Descargas*; en el iPhone se abre el menú de compartir.
- **Guardadas** (icono de marcador): las noticias guardadas se conservan aunque cambie el digest.
- **Estado de las fuentes**: pulsa el indicador "Actualizado hace…" o la tarjeta *Fuentes* para ver qué fuentes han aportado noticias y cuáles dan aviso.
- Atajos: `/` buscar · `R` actualizar · `Esc` cerrar o quitar selección. Tema claro/oscuro con el icono de la luna.

---

## Cómo está hecho

```
fetch_digest.py          Motor: fuentes RSS, categorías, keywords, score y deduplicado.
                         Descarga las 72 fuentes en paralelo (≈30 s en lugar de varios minutos).
app/ac2ality_app.py      App de escritorio: servidor local privado + ventana nativa (pywebview).
app/ac2ality.spec        Receta de PyInstaller para el .exe y el .app.
                         En Windows genera una carpeta (no un único .exe que se autoextrae):
                         arranca antes y los antivirus corporativos no la bloquean.
web/                     Interfaz única (HTML/CSS/JS) para escritorio, iPhone y navegador.
  manifest.webmanifest   Datos de instalación de la PWA.
  sw.js                  Caché sin conexión para el iPhone.
scripts/                 Iconos y scripts de compilación.
.github/workflows/
  ac2ality_digest.yml    Genera digest.json 5 veces al día y publica la web en GitHub Pages.
  build-apps.yml         Compila Windows y Mac (Intel + Apple Silicon) en la nube.
```

- Para editar fuentes, categorías o palabras clave: `fetch_digest.py` (secciones 1 a 3). El resto de piezas lo recoge solo.
- Los datos de la app de escritorio se guardan en `%LOCALAPPDATA%\Ac2ality Digest` (Windows) o `~/Library/Application Support/Ac2ality Digest` (Mac), junto a un `app.log` por si algo falla.

### Compilar a mano

Windows (PowerShell):

```powershell
.\scripts\build_windows.ps1
```

Mac (Terminal):

```bash
./scripts/build_macos.sh
```

Una app de Mac solo se puede compilar en un Mac. Si no tienes uno a mano, usa el workflow **Compilar apps de escritorio** de GitHub Actions, que compila las tres versiones. Creando una etiqueta (`git tag v2.0.0 && git push --tags`) las publica además en **Releases**.

### Probar sin compilar

```powershell
py -m pip install -r requirements-desktop.txt
py app/ac2ality_app.py
```

La línea de comandos de siempre sigue funcionando (`python fetch_digest.py` genera `digest.json`).

### ¿Y una app nativa del App Store?

La PWA cubre el uso diario en iPhone sin pasar por Apple. Publicar en el App Store exige una cuenta de Apple Developer (99 $/año), un Mac con Xcode y reescribir la descarga de noticias en Swift o JavaScript, porque iOS no ejecuta Python. Si algún día hace falta, la interfaz de `web/` se puede reutilizar dentro de esa app.
