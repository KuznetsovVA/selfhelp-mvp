# -*- coding: utf-8 -*-
"""Слой хранения данных на SQLite (стандартная библиотека).

Схема повторяет «нормированную схему таблиц» из ВКР (учётные записи,
дневниковые логи, метаданные, шкалы, заявки). SQLite выбран для MVP без
зависимостей; в промышленной версии заменяется на PostgreSQL без изменения
интерфейса этого модуля (см. README).

Примечание по безопасности: в ВКР сенситивные записи шифруются AES-256 на
уровне СУБД. В MVP записи хранятся в локальном файле БД; интерфейс
`encrypt_value`/`decrypt_value` оставлен как точка подключения шифрования.
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()

# Точка подключения шифрования AES-256 (заглушка для MVP).
def encrypt_value(value: str) -> str:
    return value


def decrypt_value(value: str) -> str:
    return value


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    """Оборачивает SQLite и предоставляет типизированные методы CRUD."""

    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self):
        config.ensure_dirs()
        with _lock, self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    consent_hash TEXT NOT NULL,
                    consent_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS diary_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    mood INTEGER,          -- самооценка настроения 1..10 (опционально)
                    source TEXT NOT NULL DEFAULT 'text',  -- 'text' | 'voice'
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id INTEGER NOT NULL REFERENCES diary_entries(id) ON DELETE CASCADE,
                    sentiment TEXT NOT NULL,
                    sentiment_score REAL NOT NULL,
                    distortions TEXT NOT NULL,  -- JSON-список
                    triggers TEXT NOT NULL,     -- JSON-список
                    technique_id INTEGER,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    scale TEXT NOT NULL,        -- 'gad7' | 'phq9'
                    answers TEXT NOT NULL,      -- JSON-массив чисел
                    score INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    crisis INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    psychologist_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at REAL NOT NULL
                );
                """
            )

    # ---- users ----
    def create_user(self, email, password_hash, password_salt, consent_hash, consent_at):
        with _lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, password_salt, consent_hash, consent_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (email, password_hash, password_salt, consent_hash, consent_at, utcnow_iso()),
            )
            return cur.lastrowid

    def get_user_by_email(self, email):
        with _lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            return dict(row) if row else None

    def get_user(self, user_id):
        with _lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    # ---- diary ----
    def add_entry(self, user_id, text, mood, source):
        with _lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO diary_entries (user_id, text, mood, source, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, text, mood, source, utcnow_iso()),
            )
            return cur.lastrowid

    def list_entries(self, user_id, limit=200):
        with _lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM diary_entries WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_entry(self, entry_id):
        with _lock, self._conn() as conn:
            row = conn.execute("SELECT * FROM diary_entries WHERE id = ?", (entry_id,)).fetchone()
            return dict(row) if row else None

    # ---- analysis ----
    def add_analysis(self, entry_id, sentiment, score, distortions, triggers, technique_id, summary):
        with _lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO analysis_results"
                " (entry_id, sentiment, sentiment_score, distortions, triggers, technique_id, summary, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (entry_id, sentiment, score, json.dumps(distortions, ensure_ascii=False),
                 json.dumps(triggers, ensure_ascii=False), technique_id, summary, utcnow_iso()),
            )
            return cur.lastrowid

    def get_analysis_for_entry(self, entry_id):
        with _lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM analysis_results WHERE entry_id = ? ORDER BY id DESC LIMIT 1",
                (entry_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_analyses(self, user_id, limit=200):
        with _lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT a.*, d.text, d.created_at AS entry_created_at"
                " FROM analysis_results a JOIN diary_entries d ON d.id = a.entry_id"
                " WHERE d.user_id = ? ORDER BY a.id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- tests ----
    def add_test_result(self, user_id, scale, answers, score, level, crisis):
        with _lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO test_results (user_id, scale, answers, score, level, crisis, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, scale, json.dumps(answers), score, level, int(crisis), utcnow_iso()),
            )
            return cur.lastrowid

    def list_test_results(self, user_id, limit=200):
        with _lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM test_results WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- requests ----
    def add_request(self, user_id, psychologist_id):
        with _lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO requests (user_id, psychologist_id, created_at) VALUES (?, ?, ?)",
                (user_id, psychologist_id, utcnow_iso()),
            )
            return cur.lastrowid

    def list_requests(self, user_id):
        with _lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM requests WHERE user_id = ? ORDER BY id DESC", (user_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- sessions (переживают перезапуск сервера) ----
    def create_session(self, token, user_id, expires_at):
        with _lock, self._conn() as conn:
            conn.execute(
                "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires_at),
            )

    def get_session(self, token):
        with _lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token = ?", (token,)
            ).fetchone()
            return dict(row) if row else None

    def delete_session(self, token):
        with _lock, self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def delete_expired_sessions(self, now):
        with _lock, self._conn() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))


db = Storage()
