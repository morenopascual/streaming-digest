#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ac2ality Digest — app de escritorio (Windows y macOS).

Abre una ventana nativa con la interfaz del digest. Todo ocurre dentro de la
app: no hay terminal, no hay que instalar Python ni abrir el navegador.

Cómo funciona:
  · Arranca un pequeño servidor local (solo 127.0.0.1, puerto aleatorio) que
    sirve la interfaz (carpeta web/) y el digest.json del usuario.
  · El botón "Actualizar" llama a /api/refresh: las fuentes RSS se descargan
    en segundo plano y la interfaz consulta /api/status para pintar el
    progreso en directo.
  · La ventana usa pywebview (WebView2 en Windows, WebKit en macOS). Si no
    estuviera disponible, se abre el navegador en modo aplicación.

Ejecutar en desarrollo:
  python app/ac2ality_app.py
"""

from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

APP_NAME = "Ac2ality Digest"
APP_VERSION = "2.0.0"

# ─── Rutas ────────────────────────────────────────────────────────────────────

if getattr(sys, "frozen", False):
    # Ejecutable de PyInstaller: los recursos están en la carpeta temporal.
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    BUNDLE_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(BUNDLE_DIR))

WEB_DIR = BUNDLE_DIR / "web"

import fetch_digest  # noqa: E402  (necesita sys.path preparado)


def user_data_dir() -> Path:
    """Carpeta escribible del usuario donde vive su digest.json."""
    override = os.environ.get("AC2_DATA_DIR")
    if override:
        Path(override).mkdir(parents=True, exist_ok=True)
        return Path(override)
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    folder = base / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


DATA_DIR = user_data_dir()
DIGEST_PATH = DATA_DIR / "digest.json"
LOG_PATH = DATA_DIR / "app.log"


def log(message: str) -> None:
    """Registro a fichero (la app no tiene consola)."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as file:
            file.write(f"{datetime.now().isoformat(timespec='seconds')}  {message}\n")
    except OSError:
        pass


def downloads_dir() -> Path:
    candidate = Path.home() / "Downloads"
    if candidate.is_dir():
        return candidate
    return DATA_DIR


# ─── Trabajo de actualización ────────────────────────────────────────────────

class RefreshJob:
    """Estado compartido de la descarga en curso, consultado por la interfaz."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = self._idle_state()

    @staticmethod
    def _idle_state() -> dict[str, Any]:
        return {
            "running": False,
            "phase": "idle",          # idle | fetching | processing | done | error
            "job_id": 0,
            "total": len(fetch_digest.FEEDS),
            "done": 0,
            "articles_so_far": 0,
            "sources": [
                {"name": name, "state": "pending", "count": 0, "error": None}
                for name, _ in fetch_digest.FEEDS
            ],
            "started_at": None,
            "finished_at": None,
            "total_articles": None,
            "sources_with_errors": None,
            "error": None,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._state["running"]:
                return json.loads(json.dumps(self._state))
            job_id = self._state["job_id"] + 1
            self._state = self._idle_state()
            self._state.update({
                "running": True,
                "phase": "fetching",
                "job_id": job_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
        threading.Thread(target=self._run, name="refresh", daemon=True).start()
        return self.snapshot()

    def _on_progress(self, event: dict[str, Any]) -> None:
        with self._lock:
            kind = event.get("type")
            if kind == "feed_start":
                self._state["sources"][event["index"]]["state"] = "loading"
            elif kind == "feed_done":
                source = self._state["sources"][event["index"]]
                source["state"] = "warning" if event.get("error") and not event.get("count") else "done"
                source["count"] = event.get("count", 0)
                source["error"] = event.get("error")
                self._state["done"] = event.get("done", self._state["done"])
                self._state["articles_so_far"] = event.get("articles_so_far", 0)
            elif kind == "processing":
                self._state["phase"] = "processing"

    def _run(self) -> None:
        started = time.time()
        try:
            output = fetch_digest.run_digest(DIGEST_PATH, progress=self._on_progress)
            with self._lock:
                self._state.update({
                    "running": False,
                    "phase": "done",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "total_articles": output["total_articles"],
                    "sources_with_errors": output["sources_with_errors"],
                })
            log(f"Actualización OK: {output['total_articles']} noticias en {time.time() - started:.1f}s")
        except Exception as exc:  # pragma: no cover - depende de la red
            log("Error en actualización:\n" + traceback.format_exc())
            with self._lock:
                self._state.update({
                    "running": False,
                    "phase": "error",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc) or exc.__class__.__name__,
                })


JOB = RefreshJob()
API_TOKEN = secrets.token_urlsafe(24)
LAST_PING = time.time()


# ─── Servidor HTTP local ─────────────────────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    server_version = "Ac2alityDigest/" + APP_VERSION

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # sin ruido: la app no tiene consola

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ── utilidades ──
    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 20 * 1024 * 1024:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Ac2-Token", ""), API_TOKEN)

    # ── GET ──
    def do_GET(self) -> None:  # noqa: N802
        global LAST_PING
        LAST_PING = time.time()
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            return self._serve_index()
        if path == "/digest.json":
            return self._serve_digest()
        if path == "/api/info":
            return self._send_json(self._info())
        if path == "/api/status":
            return self._send_json(JOB.snapshot())
        if path == "/sw.js":
            # En escritorio no hace falta service worker: evita cachés viejas.
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        return super().do_GET()

    def _serve_index(self) -> None:
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        meta = (
            f'<meta name="ac2-runtime" content="desktop">'
            f'<meta name="ac2-token" content="{API_TOKEN}">'
        )
        html = html.replace("<!--AC2_RUNTIME-->", meta, 1)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_digest(self) -> None:
        if not DIGEST_PATH.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Todavía no hay digest")
            return
        body = DIGEST_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _info() -> dict[str, Any]:
        generated_at = None
        if DIGEST_PATH.exists():
            try:
                with open(DIGEST_PATH, encoding="utf-8") as file:
                    generated_at = json.load(file).get("generated_at")
            except (OSError, ValueError):
                generated_at = None
        return {
            "runtime": "desktop",
            "app": APP_NAME,
            "version": APP_VERSION,
            "platform": platform.system(),
            "has_digest": DIGEST_PATH.exists(),
            "generated_at": generated_at,
            "total_feeds": len(fetch_digest.FEEDS),
            "data_dir": str(DATA_DIR),
        }

    # ── POST ──
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not self._authorized():
            return self._send_json({"error": "No autorizado"}, 403)

        if path == "/api/refresh":
            return self._send_json(JOB.start())
        if path == "/api/open":
            return self._open_external(self._read_json())
        if path == "/api/export":
            return self._export(self._read_json())
        return self._send_json({"error": "Ruta desconocida"}, 404)

    def _open_external(self, payload: dict[str, Any]) -> None:
        url = str(payload.get("url") or "")
        if urlparse(url).scheme not in ("http", "https"):
            return self._send_json({"ok": False, "error": "URL no válida"}, 400)
        webbrowser.open(url, new=2)
        return self._send_json({"ok": True})

    def _export(self, payload: dict[str, Any]) -> None:
        """Guarda una exportación en Descargas (en la ventana nativa no hay descargas de navegador)."""
        filename = os.path.basename(str(payload.get("filename") or "ac2ality-export.txt"))
        filename = "".join(c for c in filename if c.isalnum() or c in "-_. ") or "ac2ality-export.txt"
        content = str(payload.get("content") or "")
        target = downloads_dir() / filename
        stem, suffix = target.stem, target.suffix
        counter = 1
        while target.exists():
            target = target.with_name(f"{stem} ({counter}){suffix}")
            counter += 1
        target.write_text(content, encoding="utf-8")
        reveal_in_file_manager(target)
        return self._send_json({"ok": True, "path": str(target)})


def reveal_in_file_manager(path: Path) -> None:
    try:
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(["explorer", "/select,", str(path)])
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except OSError:
        pass


def start_server(port: int = 0) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
    return server


# ─── Ventana ─────────────────────────────────────────────────────────────────

def open_with_pywebview(url: str) -> bool:
    try:
        import webview  # pywebview
    except Exception:
        log("pywebview no disponible:\n" + traceback.format_exc())
        return False

    width, height = 1360, 900
    try:  # que quepa en portátiles pequeños
        screen = webview.screens[0]
        width = min(width, int(screen.width * 0.92))
        height = min(height, int(screen.height * 0.88))
    except Exception:
        pass

    try:
        webview.create_window(
            APP_NAME,
            url,
            width=width,
            height=height,
            min_size=(380, 600),
            background_color="#07101E",
            text_select=True,
        )
        webview.start(private_mode=False, storage_path=str(DATA_DIR / "webview"))
        return True
    except Exception:
        log("Error abriendo ventana nativa:\n" + traceback.format_exc())
        return False


def find_app_mode_browser() -> list[str] | None:
    """Edge/Chrome con --app= dan una ventana sin barras, casi como una app nativa."""
    candidates: list[str] = []
    system = platform.system()
    if system == "Windows":
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates += [
                    os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                    os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
                ]
    elif system == "Darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:
        for name in ("google-chrome", "chromium", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return [candidate]
    return None


def open_in_browser_fallback(url: str) -> None:
    """Plan B sin pywebview: navegador en modo app y servidor vivo mientras se use."""
    browser = find_app_mode_browser()
    if browser:
        subprocess.Popen(browser + [f"--app={url}", "--new-window"])
    else:
        webbrowser.open(url, new=1)

    # La interfaz hace ping cada 20 s; si se cierra la ventana, salimos.
    while True:
        time.sleep(15)
        if time.time() - LAST_PING > 90 and not JOB.snapshot()["running"]:
            break


def main() -> int:
    log(f"Inicio {APP_NAME} {APP_VERSION} en {platform.platform()}")
    if not (WEB_DIR / "index.html").exists():
        log(f"No se encuentra la interfaz en {WEB_DIR}")
        return 1

    # Opciones de desarrollo:
    #   --browser        abre el navegador en modo app en vez de la ventana nativa
    #   --serve PUERTO   solo servidor (sin ventana), útil para probar la interfaz
    port = 0
    if "--serve" in sys.argv:
        idx = sys.argv.index("--serve")
        port = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 8765

    server = start_server(port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"

    if "--serve" in sys.argv:
        print(f"{APP_NAME} sirviendo en {url}  (datos: {DATA_DIR})", flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    if "--browser" in sys.argv or not open_with_pywebview(url):
        open_in_browser_fallback(url)

    server.shutdown()
    log("Cierre normal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
