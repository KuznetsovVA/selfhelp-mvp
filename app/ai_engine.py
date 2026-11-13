# -*- coding: utf-8 -*-
"""Интеллектуальный анализ записей дневника (точка подключения ИИ).

В ВКР аналитический конвейер строится так:
  1. NLP-оценка тональности — предобученные трансформеры (BERT/RoBERTa, Hugging Face);
  2. Выявление когнитивных искажений — LLM со специализированными промптами КПТ;
  3. Поиск триггеров и подбор техник — RAG-архитектура (эмбеддинги + векторная СУБД).

Для MVP реализован детерминированный rule-based движок с тем же интерфейсом,
чтобы интерфейс работал без внешних зависимостей. Чтобы подключить реальную
модель, достаточно заменить тело метода `analyze` (см. README).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import seeds

# --- словари признаков (rule-based заглушка) ---

_POSITIVE = [
    "рад", "радост", "хорошо", "отлично", "споко", "уверен", "благодар",
    "легче", "стало лучше", "счастлив", "доволен", "получилось", "справил",
    "люблю", "нравится", "поддерж", "тепло", "надежд", "силы", "энерги",
]

_NEGATIVE = [
    "тревож", "тревог", "страшно", "страх", "боюсь", "паник", "депресс",
    "груст", "плохо", "ужас", "тяжело", "безнадёж", "безнадеж", "опустош",
    "злюсь", "злость", "раздраж", "устал", "выгорел", "выгоран", "плак",
    "одинок", "одиноч", "тоск", "больно", "невыносим", "стресс", "нервнич",
]

# Когнитивные искажения (классификаторы КПТ из ВКР).
_DISTORTIONS = [
    {
        "id": "catastrophizing",
        "name": "Катастрофизация",
        "patterns": ["катастроф", "ужасно", "кошмар", "всё пропало", "не переживу",
                     "конец света", "хуже не бывает", "не справлюсь никогда"],
    },
    {
        "id": "overgeneralization",
        "name": "Сверхобобщение",
        "patterns": ["всегда", "никогда", "всё время", "постоянно", "все так", "никто"],
    },
    {
        "id": "black_white",
        "name": "Чёрно-белое мышление",
        "patterns": ["всё или ничего", "полный провал", "идеально", "совершенно",
                     "либо всё", "или всё"],
    },
    {
        "id": "mind_reading",
        "name": "Чтение мыслей",
        "patterns": ["они думают", "он думает", "она считает", "все считают",
                     "обо мне подумают", "меня осудят", "решат, что"],
    },
    {
        "id": "should_statements",
        "name": "Долженствование",
        "patterns": ["я должен", "я должна", "обязан", "обязана", "надо было",
                     "следовало", "нельзя", "не имею права"],
    },
    {
        "id": "personalization",
        "name": "Персонализация",
        "patterns": ["из-за меня", "моя вина", "я виноват", "я виновата", "всё из-за"],
    },
    {
        "id": "labeling",
        "name": "Навешивание ярлыков",
        "patterns": ["я неудачник", "я неудачница", "я ничтожество", "я глупый",
                     "я глупая", "я лузер", "я слабак"],
    },
]

_TRIGGERS = [
    {
        "id": "work_study",
        "name": "Работа / учёба",
        "patterns": ["работа", "работе", "учёб", "учеб", "дедлайн", "экзамен",
                     "сессия", "начальник", "коллег", "универ", "диплом", "вкр",
                     "проект", "отчёт", "отчет"],
    },
    {
        "id": "relationships",
        "name": "Отношения / семья",
        "patterns": ["отношен", "партнёр", "партнер", "друг", "подруг", "ссор",
                     "разрыв", "семь", "родител", "одиноч", "близк"],
    },
    {
        "id": "sleep",
        "name": "Сон",
        "patterns": ["сон", "бессонниц", "не высыпаюсь", "спать", "просыпаюсь"],
    },
    {
        "id": "finances",
        "name": "Финансы",
        "patterns": ["деньг", "финанс", "долг", "кредит", "зарплат", "оплат"],
    },
    {
        "id": "health",
        "name": "Здоровье",
        "patterns": ["здоровь", "боле", "болит", "усталость", "устал", "самочувств"],
    },
]


@dataclass
class AnalysisResult:
    sentiment: str  # positive | negative | neutral
    sentiment_score: float  # от -1 до 1
    distortions: list[dict] = field(default_factory=list)
    triggers: list[dict] = field(default_factory=list)
    technique_id: int | None = None
    summary: str = ""


def _count_hits(text: str, patterns: list[str]) -> int:
    low = text.lower()
    return sum(1 for p in patterns if p in low)


class AIEngine:
    """Интерфейс аналитического конвейера.

    Замените `analyze` на вызов реальных моделей (BERT/RoBERTa для тональности,
    LLM для искажений, RAG для подбора техник), сохранив сигнатуру.
    """

    def analyze(self, text: str) -> AnalysisResult:
        """Анализ текста: тональность, искажения, триггеры, рекомендуемая техника."""
        pos = _count_hits(text, _POSITIVE)
        neg = _count_hits(text, _NEGATIVE)

        if pos == 0 and neg == 0:
            sentiment, score = "neutral", 0.0
        else:
            score = (pos - neg) / (pos + neg)
            score = max(-1.0, min(1.0, score))
            if score > 0.2:
                sentiment = "positive"
            elif score < -0.2:
                sentiment = "negative"
            else:
                sentiment = "neutral"

        distortions = [
            {"id": d["id"], "name": d["name"]}
            for d in _DISTORTIONS
            if _count_hits(text, d["patterns"]) > 0
        ]
        triggers = [
            {"id": t["id"], "name": t["name"]}
            for t in _TRIGGERS
            if _count_hits(text, t["patterns"]) > 0
        ]

        technique_id = self._recommend_technique(distortions, triggers)

        # Позитивной записи без искажений техника не требуется.
        if sentiment == "positive" and not distortions:
            technique_id = None

        summary = self._build_summary(sentiment, distortions, triggers, technique_id)
        return AnalysisResult(
            sentiment=sentiment,
            sentiment_score=round(score, 3),
            distortions=distortions,
            triggers=triggers,
            technique_id=technique_id,
            summary=summary,
        )

    def _recommend_technique(self, distortions, triggers) -> int | None:
        # Приоритет: техника, покрывающая найденное искажение, затем триггер.
        # Сопоставление по названиям (искажения и цели техник заданы по-русски).
        wanted = {d["name"].lower() for d in distortions}
        for t in seeds.CBT_TECHNIQUES:
            targets = {x.lower() for x in t["targets"]}
            if wanted & targets:
                return t["id"]
        # Упрощённое соответствие триггеров.
        trigger_names = {t["id"] for t in triggers}
        if "work_study" in trigger_names or "finances" in trigger_names:
            return 2  # заземление / дыхание при стрессе
        if "sleep" in trigger_names:
            return 4  # релаксация
        if "relationships" in trigger_names:
            return 5  # оспаривание мыслей
        return None

    def _build_summary(self, sentiment, distortions, triggers, technique_id) -> str:
        parts = []
        tone = {
            "positive": "преобладает позитивный эмоциональный фон",
            "negative": "преобладает негативный эмоциональный фон",
            "neutral": "эмоциональный фон нейтральный",
        }[sentiment]
        parts.append(tone)
        if distortions:
            names = ", ".join(d["name"].lower() for d in distortions)
            parts.append(f"обнаружены возможные когнитивные искажения: {names}")
        if triggers:
            names = ", ".join(t["name"].lower() for t in triggers)
            parts.append(f"вероятные триггеры: {names}")
        if technique_id:
            technique = next((t for t in seeds.CBT_TECHNIQUES if t["id"] == technique_id), None)
            if technique:
                parts.append(f"рекомендуется техника «{technique['title']}»")
        if len(parts) == 1:
            parts.append("ярко выраженных признаков не выявлено")
        return parts[0].capitalize() + "; " + "; ".join(parts[1:]) + "."


engine = AIEngine()
