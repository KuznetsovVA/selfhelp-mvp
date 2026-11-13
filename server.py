# -*- coding: utf-8 -*-
"""Точка входа HTTP-сервера MVP.

Используется только стандартная библиотека Python (http.server), поэтому
приложение запускается без установки зависимостей:

    python server.py

и открывается по адресу http://127.0.0.1:8000

Для переноса на FastAPI/uvicorn замените этот файл на ASGI-приложение, оставив
обработчики из `app/handlers.py` без изменений (см. README).
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config  # noqa: E402
from app import handlers  # noqa: E402
from app.handlers import ApiError  # noqa: E402

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".webmanifest": "application/manifest+json",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "SelfhelpMVP/1.0"

    def log_message(self, fmt, *args):  # тихий лог
        pass

    # --- helpers ---
    def _send_json(self, status: int, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_static(self, path: str):
        # нормализуем и защищаемся от выхода за пределы static/
        rel = unquote(path.lstrip("/")) or "index.html"
        full = os.path.normpath(os.path.join(config.STATIC_DIR, rel))
        if not full.startswith(os.path.normpath(config.STATIC_DIR)):
            self._send_json(403, {"error": "Forbidden"})
            return
        if not os.path.isfile(full):
            self._send_json(404, {"error": "Not found"})
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = MIME_TYPES.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # Без кэширования, чтобы после редеплоя браузер сразу брал новые css/js.
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _handle_api(self, method: str):
        parsed = urlsplit(self.path)
        body = self._read_body()
        headers = {k: v for k, v in self.headers.items()}
        try:
            result = handlers.dispatch(method, parsed.path, {}, body, headers)
            if result is None:
                self._send_json(404, {"error": "Not found"})
                return
            status, payload = result
            self._send_json(status, payload)
        except ApiError as e:
            self._send_json(e.status, {"error": e.message})
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": f"Внутренняя ошибка: {e}"})

    # --- verbs ---
    def do_GET(self):
        if self.path.startswith("/api/"):
            self._handle_api("GET")
        else:
            self._send_static(self.path)

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._handle_api("POST")
        else:
            self._send_json(404, {"error": "Not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()


def main():
    config.ensure_dirs()
    httpd = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    print(f"Сервис запущен: http://{config.HOST}:{config.PORT}")
    print("Остановка — Ctrl+C")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
