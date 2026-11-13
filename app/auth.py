# -*- coding: utf-8 -*-
"""Аутентификация и фиксация согласия.

MVP-реализация:
- пароль хэшируется SHA-256 с солью (только для демонстрации);
- согласие на обработку ПДн фиксируется хэшем документа + временной меткой,
  как описано в разделе «Модуль безопасности и защиты данных» ВКР.

Для промышленного использования заменить на bcrypt/argon2 и JWT/OAuth2.
"""
import hashlib
import secrets
import time

from . import config, storage

# Документ согласия (единая форма, которую пользователь принимает при регистрации).
CONSENT_TEXT = (
    "Я даю согласие на обработку моих персональных данных в соответствии с "
    "Федеральным законом № 152-ФЗ «О персональных данных»."
)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Возвращает (соль, хэш)."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return salt, digest


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, digest = hash_password(password, salt)
    return secrets.compare_digest(digest, expected_hash)


def consent_hash(text: str) -> str:
    """SHA-256 хэш принятого документа согласия (для фиксации, без хранения текста)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SessionStore:
    """Хранилище сессий в БД (переживают перезапуск сервера)."""

    def create(self, user_id: int) -> str:
        token = secrets.token_hex(32)
        storage.db.create_session(token, user_id, time.time() + config.SESSION_TTL_SECONDS)
        return token

    def get_user_id(self, token: str) -> int | None:
        row = storage.db.get_session(token)
        if row is None:
            return None
        if time.time() > row["expires_at"]:
            storage.db.delete_session(token)
            return None
        return row["user_id"]

    def revoke(self, token: str) -> None:
        storage.db.delete_session(token)


sessions = SessionStore()
