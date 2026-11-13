# -*- coding: utf-8 -*-
"""Общие настройки и пути приложения.

Все пути считаются относительно расположения этого файла, чтобы приложение
запускалось из любого рабочего каталога.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Хост/порт берутся из окружения, чтобы работать на PaaS (Render и др.),
# которые сами задают PORT и требуют слушать 0.0.0.0.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

# Путь к БД можно переопределить (напр. на persistent-диск в облаке).
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(DATA_DIR, "selfhelp.db"))

# Название приложения (используется на фронтенде и в отчётах).
APP_NAME = "Самопомощь"

# Время жизни сессии. Сессии хранятся в БД (переживают перезапуск).
# В промышленной версии заменить на OAuth2/JWT (см. README).
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 дней

def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
