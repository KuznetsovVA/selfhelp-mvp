# -*- coding: utf-8 -*-
"""REST-обработчики (слой «роутера»).

Каждый обработчик возвращает (HTTP-статус, dict). Сервер сериализует dict в JSON.
Этот слой при переносе на FastAPI превращается в обычные route-функции без
изменения бизнес-логики (см. README).
"""
from __future__ import annotations

from . import auth, scales, seeds, storage
from .ai_engine import engine


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _json(value):
    return value


def _require_auth(headers) -> int:
    token = _bearer_token(headers)
    if not token:
        raise ApiError(401, "Требуется авторизация")
    user_id = auth.sessions.get_user_id(token)
    if user_id is None:
        raise ApiError(401, "Сессия недействительна или истекла")
    return user_id


def _bearer_token(headers) -> str | None:
    value = headers.get("Authorization", "") or headers.get("authorization", "")
    if value.startswith("Bearer "):
        return value[len("Bearer "):].strip()
    return None


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "created_at": user["created_at"]}


# ---- auth ----

def handle_register(body):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    consent = bool(body.get("consent"))
    if not email or "@" not in email:
        raise ApiError(400, "Укажите корректный email")
    if len(password) < 6:
        raise ApiError(400, "Пароль должен быть не короче 6 символов")
    if not consent:
        raise ApiError(400, "Необходимо согласие на обработку персональных данных")
    if storage.db.get_user_by_email(email):
        raise ApiError(409, "Пользователь с таким email уже существует")

    salt, pwd_hash = auth.hash_password(password)
    consent_hash = auth.consent_hash(auth.CONSENT_TEXT)
    user_id = storage.db.create_user(email, pwd_hash, salt, consent_hash, storage.utcnow_iso())
    user = storage.db.get_user(user_id)
    token = auth.sessions.create(user_id)
    return 201, {"token": token, "user": _public_user(user), "consent_hash": consent_hash}


def handle_login(body):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    user = storage.db.get_user_by_email(email)
    if not user or not auth.verify_password(password, user["password_salt"], user["password_hash"]):
        raise ApiError(401, "Неверный email или пароль")
    token = auth.sessions.create(user["id"])
    return 200, {"token": token, "user": _public_user(user)}


def handle_logout(headers):
    token = _bearer_token(headers)
    if token:
        auth.sessions.revoke(token)
    return 200, {"ok": True}


def handle_me(user_id):
    user = storage.db.get_user(user_id)
    return 200, {"user": _public_user(user) if user else None}


# ---- diary ----

def handle_diary_list(user_id):
    entries = storage.db.list_entries(user_id)
    result = []
    for e in entries:
        a = storage.db.get_analysis_for_entry(e["id"])
        result.append({
            "id": e["id"],
            "text": e["text"],
            "mood": e["mood"],
            "source": e["source"],
            "created_at": e["created_at"],
            "analysis": _analysis_view(a),
        })
    return 200, {"entries": result}


def handle_diary_create(user_id, body):
    text = (body.get("text") or "").strip()
    if not text:
        raise ApiError(400, "Запись не может быть пустой")
    mood = body.get("mood")
    if mood is not None:
        try:
            mood = int(mood)
            mood = max(1, min(10, mood))
        except (TypeError, ValueError):
            mood = None
    source = body.get("source") if body.get("source") in ("text", "voice") else "text"

    entry_id = storage.db.add_entry(user_id, text, mood, source)

    analysis = engine.analyze(text)
    storage.db.add_analysis(
        entry_id,
        analysis.sentiment,
        analysis.sentiment_score,
        analysis.distortions,
        analysis.triggers,
        analysis.technique_id,
        analysis.summary,
    )
    entry = storage.db.get_entry(entry_id)
    saved = storage.db.get_analysis_for_entry(entry_id)
    return 201, {
        "entry": {**entry},
        "analysis": _analysis_view(saved),
    }


def _analysis_view(a):
    if not a:
        return None
    return {
        "sentiment": a["sentiment"],
        "sentiment_score": a["sentiment_score"],
        "distortions": _parse_json(a["distortions"]),
        "triggers": _parse_json(a["triggers"]),
        "technique_id": a["technique_id"],
        "summary": a["summary"],
    }


def _parse_json(value):
    import json
    if not value:
        return []
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return []


# ---- tests ----

def handle_test_spec(scale):
    spec = scales.SCALES.get(scale)
    if not spec:
        raise ApiError(404, "Неизвестная шкала")
    return 200, {
        "scale": spec["scale"],
        "title": spec["title"],
        "instruction": spec["instruction"],
        "questions": spec["questions"],
        "options": scales.OPTIONS,
    }


def handle_test_submit(user_id, body):
    scale = body.get("scale")
    spec = scales.SCALES.get(scale)
    if not spec:
        raise ApiError(404, "Неизвестная шкала")
    answers = body.get("answers")
    if not isinstance(answers, list) or len(answers) != len(spec["questions"]):
        raise ApiError(400, "Некорректные ответы")
    try:
        answers = [int(a) for a in answers]
    except (TypeError, ValueError):
        raise ApiError(400, "Ответы должны быть числами")
    if any(a < 0 or a > 3 for a in answers):
        raise ApiError(400, "Ответы вне допустимого диапазона")

    score, level, crisis = scales.interpret(scale, answers)
    result_id = storage.db.add_test_result(user_id, scale, answers, score, level, crisis)
    return 201, {
        "id": result_id,
        "scale": scale,
        "score": score,
        "level": level,
        "crisis": crisis,
    }


# ---- techniques / psychologists / crisis ----

def handle_techniques_list():
    return 200, {"techniques": seeds.CBT_TECHNIQUES}


def handle_technique_detail(tid):
    for t in seeds.CBT_TECHNIQUES:
        if t["id"] == tid:
            return 200, {"technique": t}
    raise ApiError(404, "Техника не найдена")


def handle_psychologists():
    return 200, {"psychologists": seeds.PSYCHOLOGISTS}


def handle_crisis():
    return 200, {"contacts": seeds.CRISIS_CONTACTS, "disclaimer": seeds.DISCLAIMER}


def handle_request_create(user_id, body):
    psychologist_id = body.get("psychologist_id")
    if psychologist_id not in {p["id"] for p in seeds.PSYCHOLOGISTS}:
        raise ApiError(404, "Психолог не найден")
    request_id = storage.db.add_request(user_id, psychologist_id)
    return 201, {"id": request_id, "status": "new"}


# ---- progress / report ----

def handle_progress(user_id):
    entries = storage.db.list_entries(user_id, limit=500)
    mood_series = [
        {"t": e["created_at"], "value": e["mood"]}
        for e in reversed(entries)
        if e["mood"] is not None
    ]
    tests = storage.db.list_test_results(user_id, limit=500)
    test_series = [
        {"t": t["created_at"], "scale": t["scale"], "score": t["score"], "level": t["level"]}
        for t in reversed(tests)
    ]
    return 200, {"mood": mood_series, "tests": test_series}


def handle_report(user_id):
    analyses = storage.db.list_analyses(user_id, limit=1000)
    distortion_counts: dict[str, int] = {}
    trigger_counts: dict[str, int] = {}
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    technique_counts: dict[str, int] = {}

    for a in analyses:
        sentiment_counts[a["sentiment"]] = sentiment_counts.get(a["sentiment"], 0) + 1
        for d in _parse_json(a["distortions"]):
            distortion_counts[d["name"]] = distortion_counts.get(d["name"], 0) + 1
        for t in _parse_json(a["triggers"]):
            trigger_counts[t["name"]] = trigger_counts.get(t["name"], 0) + 1
        tid = a["technique_id"]
        if tid:
            technique_counts[str(tid)] = technique_counts.get(str(tid), 0) + 1

    tests = storage.db.list_test_results(user_id, limit=500)
    test_history = [
        {"t": t["created_at"], "scale": t["scale"], "score": t["score"], "level": t["level"], "crisis": bool(t["crisis"])}
        for t in reversed(tests)
    ]

    return 200, {
        "sentiment": sentiment_counts,
        "distortions": distortion_counts,
        "triggers": trigger_counts,
        "techniques": technique_counts,
        "tests": test_history,
        "entries_count": len(analyses),
    }


# ---- router ----

_ROUTES = []  # (method, regex, handler)


def _route(method, pattern):
    def deco(fn):
        _ROUTES.append((method, pattern, fn))
        return fn
    return deco


@_route("POST", r"^/api/register$")
def _r_register(method, path, query, body, headers):
    return handle_register(body)


@_route("POST", r"^/api/login$")
def _r_login(method, path, query, body, headers):
    return handle_login(body)


@_route("POST", r"^/api/logout$")
def _r_logout(method, path, query, body, headers):
    return handle_logout(headers)


@_route("GET", r"^/api/me$")
def _r_me(method, path, query, body, headers):
    return handle_me(_require_auth(headers))


@_route("GET", r"^/api/crisis$")
def _r_crisis(method, path, query, body, headers):
    return handle_crisis()


@_route("GET", r"^/api/diary$")
def _r_diary_list(method, path, query, body, headers):
    return handle_diary_list(_require_auth(headers))


@_route("POST", r"^/api/diary$")
def _r_diary_create(method, path, query, body, headers):
    return handle_diary_create(_require_auth(headers), body)


@_route("GET", r"^/api/tests/(gad7|phq9)$")
def _r_test_spec(method, path, query, body, headers, scale=None):
    return handle_test_spec(scale)


@_route("POST", r"^/api/tests/submit$")
def _r_test_submit(method, path, query, body, headers):
    return handle_test_submit(_require_auth(headers), body)


@_route("GET", r"^/api/techniques$")
def _r_techniques(method, path, query, body, headers):
    return handle_techniques_list()


@_route("GET", r"^/api/psychologists$")
def _r_psychologists(method, path, query, body, headers):
    return handle_psychologists()


@_route("POST", r"^/api/requests$")
def _r_requests(method, path, query, body, headers):
    return handle_request_create(_require_auth(headers), body)


@_route("GET", r"^/api/progress$")
def _r_progress(method, path, query, body, headers):
    return handle_progress(_require_auth(headers))


@_route("GET", r"^/api/report$")
def _r_report(method, path, query, body, headers):
    return handle_report(_require_auth(headers))


def dispatch(method, path, query, body, headers):
    """Возвращает (status, dict) или None, если маршрут не найден."""
    import re
    for m, pattern, fn in _ROUTES:
        if m != method:
            continue
        match = re.match(pattern, path)
        if match:
            kwargs = {}
            if match.groups():
                kwargs["scale"] = match.group(1)
            return fn(method, path, query, body, headers, **kwargs)
    return None
