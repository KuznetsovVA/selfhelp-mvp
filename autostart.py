#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Автозапуск сервиса «Самопомощь».

Одной командой:
  1. проверяет, что порт свободен (или сервер уже запущен);
  2. поднимает локальный сервер;
  3. ждёт, пока он начнёт отвечать;
  4. открывает публичный туннель (если доступен ssh);
  5. печатает ссылки и ждёт Ctrl+C, чтобы всё аккуратно остановить.

Запуск:
    python autostart.py              # сервер + публичный туннель
    python autostart.py --no-tunnel  # только локальный сервер
    python autostart.py --port 8080  # другой порт
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TUNNEL_HOST = "nokey@localhost.run"


# --- Кириллица в консоли Windows: переключаем вывод на UTF-8 ---------------
def _setup_console_encoding() -> None:
    """Windows-консоль по умолчанию в cp1251 и портит русский текст."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # 65001 — UTF-8
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_setup_console_encoding()


# --------------------------------------------------------------------------- #
#  Вспомогательные функции
# --------------------------------------------------------------------------- #
def find_python() -> str:
    """Возвращает путь к интерпретатору для дочернего процесса."""
    return sys.executable


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def server_responds(port: int, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def find_ssh() -> str | None:
    """Ищет ssh: сначала PATH, затем стандартный каталог Windows."""
    found = shutil.which("ssh")
    if found:
        return found
    candidates = [
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                     "System32", "OpenSSH", "ssh.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def find_cloudflared() -> str | None:
    """Ищет cloudflared в PATH или в папке tools проекта."""
    found = shutil.which("cloudflared")
    if found:
        return found
    local = os.path.join(BASE_DIR, "tools", "cloudflared.exe")
    if os.path.isfile(local):
        return local
    return None


# --------------------------------------------------------------------------- #
#  Вывод
# --------------------------------------------------------------------------- #
class Colors:
    enabled = sys.stdout.isatty() and os.name != "nt" or (
        os.name == "nt" and "WT_SESSION" in os.environ
    )

    @classmethod
    def wrap(cls, code: str, text: str) -> str:
        if not cls.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    @classmethod
    def green(cls, t):
        return cls.wrap("32", t)

    @classmethod
    def yellow(cls, t):
        return cls.wrap("33", t)

    @classmethod
    def red(cls, t):
        return cls.wrap("31", t)

    @classmethod
    def cyan(cls, t):
        return cls.wrap("36", t)

    @classmethod
    def bold(cls, t):
        return cls.wrap("1", t)


def banner(text: str) -> None:
    line = "=" * 56
    print()
    print(Colors.cyan(line))
    print(Colors.bold(f"  {text}"))
    print(Colors.cyan(line))


# --------------------------------------------------------------------------- #
#  Туннель
# --------------------------------------------------------------------------- #
class Tunnel:
    """Публичный туннель к локальному порту."""

    def __init__(self, port: int):
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.url: str | None = None
        self.kind: str | None = None
        self._stop = False

    def start(self) -> bool:
        cloudflared = find_cloudflared()
        if cloudflared:
            return self._start_cloudflared(cloudflared)
        ssh = find_ssh()
        if ssh:
            return self._start_ssh(ssh)
        return False

    def _start_cloudflared(self, exe: str) -> bool:
        self.kind = "cloudflared"
        self.proc = subprocess.Popen(
            [exe, "tunnel", "--url", f"http://localhost:{self.port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=self._read_output, args=(r"https://[a-z0-9-]+\.trycloudflare\.com",), daemon=True).start()
        return True

    def _start_ssh(self, ssh: str) -> bool:
        self.kind = "localhost.run"
        self.proc = subprocess.Popen(
            [
                ssh,
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=NUL" if os.name == "nt" else "-o UserKnownHostsFile=/dev/null",
                "-o", "ServerAliveInterval=30",
                "-o", "ExitOnForwardFailure=yes",
                "-R", f"80:localhost:{self.port}",
                TUNNEL_HOST,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(
            target=self._read_output,
            args=(r"https://[a-z0-9]+\.(?:app\.)?lhr\.life",),
            daemon=True,
        ).start()
        return True

    def _read_output(self, pattern: str) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            if self._stop:
                break
            match = re.search(pattern, line)
            if match and not self.url:
                self.url = match.group(0)
                print()
                print(Colors.green("  Публичная ссылка готова:"))
                print(Colors.bold(f"  {self.url}"))
                print(Colors.yellow("  Открывается без VPN. Ссылка живёт, пока открыто это окно."))
                print()

    def wait_for_url(self, timeout: float = 25.0) -> str | None:
        start = time.time()
        while time.time() - start < timeout:
            if self.url:
                return self.url
            if self.proc and self.proc.poll() is not None:
                return None
            time.sleep(0.3)
        return self.url

    def stop(self) -> None:
        self._stop = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass


# --------------------------------------------------------------------------- #
#  Основной сценарий
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="Автозапуск сервиса «Самопомощь»")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)),
                        help="порт (по умолчанию 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="адрес прослушивания")
    parser.add_argument("--no-tunnel", action="store_true", help="без публичного туннеля")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    args = parser.parse_args()

    port = args.port
    banner("Самопомощь — автозапуск")

    # --- 1. Проверяем, не запущен ли уже сервер -----------------------------
    if server_responds(port):
        print(Colors.yellow(f"  Сервер уже работает на порту {port}."))
        print(f"  Локально:  http://127.0.0.1:{port}")
        print()
        print("  Если нужен публичный туннель к нему:")
        print(Colors.cyan(f"    {find_ssh() or 'ssh'} -R 80:localhost:{port} nokey@localhost.run"))
        return 0

    if not port_is_free(args.host, port):
        print(Colors.red(f"  Порт {port} занят другой программой."))
        print(f"  Освободите его или укажите другой: --port {port + 1}")
        return 1

    # --- 2. Запускаем сервер ------------------------------------------------
    print(f"  Запускаю сервер на порту {port} ...")
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = args.host
    env["PYTHONIOENCODING"] = "utf-8"

    server_proc = subprocess.Popen(
        [find_python(), os.path.join(BASE_DIR, "server.py")],
        cwd=BASE_DIR,
        env=env,
    )

    # --- 3. Ждём готовности -------------------------------------------------
    ready = False
    for _ in range(60):  # до 15 секунд
        if server_responds(port):
            ready = True
            break
        if server_proc.poll() is not None:
            break
        time.sleep(0.25)

    if not ready:
        print(Colors.red("  Сервер не запустился."))
        if server_proc.poll() is None:
            server_proc.terminate()
        return 1

    print(Colors.green(f"  Сервер готов:  http://127.0.0.1:{port}"))

    # --- 4. Открываем браузер ----------------------------------------------
    if not args.no_browser:
        try:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}")
        except Exception:
            pass

    # --- 5. Поднимаем туннель ----------------------------------------------
    tunnel = None
    if not args.no_tunnel:
        print("  Поднимаю публичный туннель ...")
        tunnel = Tunnel(port)
        if not tunnel.start():
            print(Colors.yellow("  Туннель недоступен: не найден ни cloudflared, ни ssh."))
            print("  Локальный доступ продолжает работать.")
            tunnel = None
        else:
            url = tunnel.wait_for_url()
            if not url:
                print(Colors.yellow("  Не удалось получить публичную ссылку."))
                print("  Туннель остановлен; локальный доступ работает.")
                tunnel.stop()
                tunnel = None

    # --- 6. Итоговая подсказка ---------------------------------------------
    print()
    print(Colors.cyan("-" * 56))
    print(Colors.bold("  Работает:"))
    print(f"    Локально:  http://127.0.0.1:{port}")
    if tunnel and tunnel.url:
        print(f"    Публично:  {tunnel.url}")
    print()
    print("  Остановить всё — Ctrl+C")
    print(Colors.cyan("-" * 56))

    # --- 7. Ожидание остановки ---------------------------------------------
    stop_event = threading.Event()

    def handle_signal(signum, frame):
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
    except Exception:
        pass

    try:
        while not stop_event.is_set():
            if server_proc.poll() is not None:
                print(Colors.yellow("\n  Сервер завершил работу."))
                break
            if tunnel and tunnel.proc and tunnel.proc.poll() is not None:
                print(Colors.yellow("\n  Туннель закрылся (ссылка больше не работает)."))
                print("  Локальный доступ продолжает работать.")
                tunnel = None
            stop_event.wait(0.5)
    except KeyboardInterrupt:
        pass

    # --- 8. Аккуратная остановка -------------------------------------------
    print("\n  Останавливаю ...")
    if tunnel:
        tunnel.stop()
    if server_proc.poll() is None:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
    print(Colors.green("  Готово. До связи!"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
