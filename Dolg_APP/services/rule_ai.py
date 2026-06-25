"""Self-hosted AI assistant built from deterministic engineering facts.

The module deliberately stays lightweight: no external LLM and no neural runtime.
It turns ProjectReview, scheme JSON, measurements, BOM and expert findings into
short answers that look like a useful demo assistant rather than a static FAQ.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter

from . import ai_algorithms, ai_render
from .ai_retrieval import build_retrieval_context
from .ai_retrieval import retrieval_lines as ai_retrieval_lines
from .artifact_learning import artifact_training_summary, learning_suggestions_from_artifacts
from .project_review import build_design_review
from .review_i18n import (
    build_measurement_rows,
    topology_label_ru,
    translate_finding,
    translate_review_text,
)

TYPE_LABELS_RU = {
    'battery': 'источник',
    'current_source': 'источник тока',
    'ground': 'GND',
    'resistor': 'резистор',
    'capacitor': 'конденсатор',
    'inductor': 'индуктивность',
    'led': 'LED',
    'diode': 'диод',
    'transistor': 'транзистор',
    'npn': 'NPN',
    'pnp': 'PNP',
    'ic': 'микросхема',
    'regulator': 'стабилизатор',
    'button': 'кнопка',
    'node': 'узел',
}

INTENT_LABELS_RU = {
    'overview': 'краткий разбор схемы',
    'scheme_overview': 'разбор схемы',
    'fix_plan': 'план исправления',
    'why_failed': 'почему не проходит проверка',
    'recommend': 'подбор номиналов и компонентов',
    'thermal': 'запас по мощности и температуре',
    'measurement': 'измерения и expected vs measured',
    'gnd': 'опорный узел GND',
    'bom': 'BOM, каталог и заказ',
    'learning': 'учебное задание по ошибке',
    'create_task': 'учебное задание из ошибки',
    'import': 'CAD/SPICE-импорт',
    'formula': 'формула и расчет',
    'compare': 'сравнение вариантов',
    'demo_script': 'сценарий для защиты',
}

KEYWORD_INTENTS = (
    ('gnd', ('gnd', 'ground', 'земл', 'ноль', 'опорн')),
    ('demo_script', ('защит', 'презентац', 'демо', 'показать комиссии', 'как рассказать')),
    ('create_task', ('создай задание', 'сделай задание', 'учебное задание', 'задание из ошибки')),
    (
        'why_failed',
        ('почему не проходит', 'почему падает', 'почему ошибка', 'не проходит', 'failed', 'fail', '500'),
    ),
    (
        'measurement',
        (
            'измер',
            'осцилл',
            'мультим',
            'probe',
            'пробник',
            'expected',
            'measured',
            'напряж',
            'ток ветв',
            'branch_current',
            'rms',
            'частот',
            'duty',
            'dc',
            'ac',
            'tran',
            'симуляц',
        ),
    ),
    ('formula', ('формул', 'рассчитай', 'расчет', 'посчитай', 'ом', 'ohm', 'rc cutoff', 'ne555')),
    ('compare', ('сравни', 'лучше', 'хуже', 'вариант', 'альтернатив', 'vs', 'или')),
    ('thermal', ('перегрев', 'тепл', 'температ', 'запас', 'мощност', 'power', 'thermal')),
    ('bom', ('bom', 'заказ', 'корзин', 'каталог', 'товар', 'налич', 'цена', 'spice', 'cad model', 'модель')),
    ('learning', ('обуч', 'урок', 'задан', 'практик', 'тест', 'как ученику')),
    ('import', ('импорт', 'import', 'ltspice', 'kicad', 'spice', 'netlist', 'нетлист', 'asc')),
    ('recommend', ('подбери', 'подбор', 'номинал', 'value', 'резистор выбрать', 'какой компонент', 'analog')),
    ('fix_plan', ('исправ', 'план', 'ошиб', 'критич', 'проверь', 'что не так', 'risk', 'drc', 'erc')),
)

OPENINGS = {
    # Каждый intent имеет 5-8 шаблонов с разной структурой:
    # — императивные («Беру…», «Смотрю…»), декларативные («Сейчас…»),
    #   вопросительные («Знаешь, что…»), фактические («Топология такова:…»).
    # Перфикс «**Self AI:**» оставлен НЕ во всех — добавляет роботичности.
    # Параметры {score} и {status} опциональны — можно строить ответ без них.
    'overview': (
        '**Self AI:** коротко разбираю схему по фактам review: оценка {score}/100, статус: {status}.',
        '**Self AI:** смотрю на схему как на инженерный отчёт: {score}/100, статус: {status}.',
        'Сначала паспорт схемы, потом риски. Текущая оценка {score}/100, статус — {status}.',
        'Начну с фактов: оценка {score}/100, статус {status}. Дальше — что обращает на себя внимание.',
        'Беру review и иду по нему: {score}/100 ({status}). Покажу, что в схеме работает, а что — нет.',
        'Схема выглядит так: {score}/100, статус {status}. Перевожу это в инженерный язык.',
        'Не угадываю — отвечаю по trace из review. Сейчас {score}/100, статус {status}.',
    ),
    'scheme_overview': (
        '**Self AI:** разбираю текущую схему по топологии, компонентам и review: {score}/100, статус: {status}.',
        'Даю инженерный обзор схемы, не общий пересказ. Сейчас {score}/100, статус {status}.',
        'Схема как «инженерный фрагмент»: топология + компоненты + риски. Оценка {score}/100.',
        'Распакую по слоям: топология → состав → проблемы. Статус: {status}, оценка {score}/100.',
        'Это разбор по review, не свободное описание. Текущий статус: {status} ({score}/100).',
        'Начну с того, что схема пытается делать, потом — что в ней мешает. Score: {score}/100.',
    ),
    'fix_plan': (
        '**Self AI:** собираю план исправления по DRC/ERC и экспертным правилам: {score}/100, статус: {status}.',
        'Иду от критичных ошибок к проверкам. Текущая оценка {score}/100, статус {status}.',
        'Это не свободный чат, а trace по review: {score}/100, статус {status}.',
        'Что исправлять — в порядке риска. Errors первыми, recommendations последними. Score: {score}/100.',
        'План будет адресный: rule_id → действие → проверка. Сейчас {score}/100 ({status}).',
        'Беру эксперт-findings и режу план на шаги. Оценка проекта {score}/100, статус {status}.',
        'Главное — не «вообще всё исправить», а закрыть critical-ошибки. Сейчас {score}/100.',
    ),
    'why_failed': (
        '**Self AI:** ищу причину сбоя по ошибкам, warning-ам и expert findings: {score}/100, статус: {status}.',
        'Объясняю, почему проверка может не проходить. Сейчас {score}/100, статус {status}.',
        'Failure — это всегда конкретный rule_id, не «что-то не так». Разбираю по facts. Score: {score}/100.',
        'Начну с самых громких errors, потом покажу, что они тянут за собой. Статус: {status}.',
        'Если есть критичные DRC/ERC — они и есть причина. Если их нет — смотрим warnings. Score {score}/100.',
        'Откуда «не работает»: чаще всего это GND, источник или несоединённый компонент. Проверяю это здесь.',
    ),
    'recommend': (
        '**Self AI:** подбираю через ограничения схемы, review и каталог. Оценка проекта {score}/100, статус: {status}.',
        'Сначала проверяю условия, потом номиналы и наличие. Сейчас {score}/100, статус {status}.',
        'Подбор начинаю с электрических ограничений, не с красивого ответа. Оценка {score}/100.',
        'Чтобы рекомендовать — мне нужны цель и ограничение. Из review уже взято: статус {status}.',
        'Считаю по формулам, проверяю по review, отдаю с обоснованием. Текущий score: {score}/100.',
        'Подбор «по принципу» — это всегда: что нужно, какие ограничения, что есть в каталоге.',
        'Не рекомендую от балды. Сначала — расчёт. Потом — каталог. Сейчас оценка {score}/100.',
    ),
    'thermal': (
        '**Self AI:** проверяю мощность, температуру и инженерный запас: {score}/100, статус: {status}.',
        'Смотрю derating-слой: где может греться, где не хватает запаса. Оценка {score}/100, статус {status}.',
        'Мощность и температура — две вещи, которые «убивают» компонент чаще всего. Беру их первыми.',
        'Запас по мощности нормальный — 30-50% от datasheet. Проверю, что в схеме так. Score: {score}/100.',
        'Тепловой анализ это не «сколько Вт» — это «что переживёт деградацию». Поясню по компонентам.',
        'Греется не от номинала, а от ситуации (ток × напряжение, длительность). Разбираю по review.',
    ),
    'measurement': (
        '**Self AI:** перехожу в режим лаборатории: расчёт → симуляция → измерение. Оценка {score}/100, статус: {status}.',
        'Отвечаю через expected vs measured и сохранённые метрики. Сейчас {score}/100, статус {status}.',
        'Измерение — главный аргумент против «должно работать». Смотрю, что уже измерено.',
        'Сначала: что нужно измерить и где. Потом: какой ожидаемый результат. Score {score}/100.',
        'Если есть симуляция — сравню с расчётом. Если нет — предложу, что запустить. Статус {status}.',
        'Измерение без expected — это не измерение. Покажу, как закрыть пробелы. Текущая оценка {score}/100.',
    ),
    'gnd': (
        '**Self AI:** отдельно проверяю GND и пути до опорного узла. Оценка {score}/100, статус: {status}.',
        'GND важен для рабочей точки и SPICE, поэтому начинаю с него. Сейчас {score}/100, статус {status}.',
        'Без GND — нет нулевого потенциала, и SPICE «сходит с ума». Проверю, есть ли он и куда идёт.',
        'Если у тебя «непонятная симуляция» — на 80% это GND или несоединённый узел. Сейчас {score}/100.',
        'Опорный узел — это не «земля» как в проводке, а математический ноль для решения. Поясню разницу.',
        '«Floating ground» — это когда GND есть, но не подключён куда надо. Проверим это в твоей схеме.',
    ),
    'bom': (
        '**Self AI:** смотрю связку схема → товар → BOM → заказ. Оценка {score}/100, статус: {status}.',
        'Проверяю каталог, модели и риски закупки. Сейчас {score}/100, статус {status}.',
        'BOM — это не список деталей, это план закупки. Смотрю, что в каталоге, что под угрозой EOL.',
        'Каждый компонент схемы → товар → цена. Если что-то «не привязано» — это будущий блок при заказе.',
        'BOM-риски бывают двух типов: «нет в каталоге» и «есть, но кончится». Различаю их в review.',
        'Спрашивай BOM-вопросы — отвечу через snapshot каталога, не догадки. Score: {score}/100.',
    ),
    'learning': (
        '**Self AI:** превращаю найденные ошибки в практикум. Оценка проекта {score}/100, статус: {status}.',
        'Из review можно сделать учебный сценарий: ошибка, исправление, измерение. Сейчас {score}/100, статус {status}.',
        'Ошибка в схеме — это хороший учебный кейс. Покажу, как сделать из неё урок с проверкой.',
        'Лучшее обучение — когда ты сам нашёл ошибку и сам её исправил. Превращаю в задание.',
        'Не «обучение в вакууме», а «обучение по живой схеме». Беру твою проблему и оформляю как урок.',
    ),
    'create_task': (
        '**Self AI:** собираю учебное задание из текущего finding/review: {score}/100, статус: {status}.',
        'Превращаю инженерную ошибку в практикум с проверкой. Сейчас {score}/100, статус {status}.',
        'Задание = условие + критерий проверки + подсказка. Все три беру из review.',
        'Не абстрактная задача, а «реши то, что у тебя не работает». Оформлю как задание.',
        'Беру конкретный rule_id из твоего review и собираю учебный кейс вокруг него. Score: {score}/100.',
    ),
    'import': (
        '**Self AI:** проверяю импорт как вход в review, а не как слепую конвертацию. Оценка {score}/100, статус: {status}.',
        'После CAD/SPICE-импорта главное не потерять warnings и unsupported элементы. Сейчас {score}/100, статус {status}.',
        'Хороший импорт — это не «100% совпадение», это «выявлены все различия». Покажу, что внутри.',
        'Если KiCad/LTspice показал unsupported — это полезная диагностика, а не баг. Объясню.',
        'Импорт без последующего review — это просто конвертация. Я добавлю review-слой. Score {score}/100.',
    ),
    'formula': (
        '**Self AI:** отвечаю через расчёт и формулу, а затем сверяю с review: {score}/100, статус: {status}.',
        'Сначала формула, потом инженерная проверка результата. Сейчас {score}/100, статус {status}.',
        'Формула без подстановки реальных значений — пустая. Подставлю из твоей схемы.',
        'Закон Ома, RC cutoff, делитель напряжения — это не магия, это арифметика. Покажу шаг за шагом.',
        'Возьму формулу из теории, подставлю твои номиналы, сверю с симуляцией. Текущий score: {score}/100.',
    ),
    'compare': (
        '**Self AI:** сравниваю варианты по электрическим ограничениям, BOM и рискам: {score}/100, статус: {status}.',
        'Сравнение делаю через факты проекта, а не вкусовщину. Сейчас {score}/100, статус {status}.',
        'Сравнение по 4 критериям: что работает, чем дешевле, чем надёжнее, что есть в каталоге.',
        'Не «лучше/хуже вообще», а «лучше для этой схемы». Беру контекст из review. Score: {score}/100.',
        '«Какой из» — нужно знать «для чего». Проясню условие, потом сравню. Статус {status}.',
    ),
    'demo_script': (
        '**Self AI:** готовлю краткий сценарий объяснения схемы для защиты: {score}/100, статус: {status}.',
        'Перевожу инженерный trace в речь для демонстрации. Сейчас {score}/100, статус {status}.',
        'Сценарий для защиты = что показать + что сказать + какой вопрос ожидать. Соберу всё три.',
        'Не пересказ кода, а демо-логика: «вот была проблема → вот как нашёл → вот как закрыл».',
        'Защита проходит лучше, когда ты показываешь не только результат, но и trace. Помогу выстроить.',
        '«За 3 минуты объясни схему» — реально, если структура такая: 1) что делает 2) что в ней нового 3) как проверил.',
    ),
    # ── Новые intents (раньше fall-through на overview) ───────────────────
    'greeting': (
        'Привет. Чем могу помочь по этой схеме?',
        'Здравствуй! Я могу разобрать схему, объяснить ошибки или подобрать компоненты.',
        'Привет. Если есть конкретный вопрос про схему — задавай. Если нет — могу начать с обзора.',
    ),
    'unknown': (
        'Не уверен, что понял запрос. Можешь переформулировать ближе к схеме? Например: «почему DC падает», «что измерить», «подбери R для делителя».',
        'Пока непонятно, что нужно. Я отвечаю по инженерному trace — попробуй задать вопрос про конкретный элемент или симуляцию.',
        'Если вопрос про схему — могу помочь. Если нет — лучше уточни, а то отвечу не по теме.',
    ),
    'no_data': (
        'Схема пустая или не сохранена. Сначала добавь хотя бы 2-3 компонента и GND, тогда я смогу что-то сказать.',
        'Чтобы дать инженерный ответ, нужна схема в редакторе. Сейчас она пустая.',
        'Без компонентов мне не на что опереться. Добавь источник + резистор + GND и спроси снова.',
    ),
}

FOLLOWUP_MARKERS = (
    'а почему',
    'почему?',
    'почему это',
    'а если',
    'и что',
    'что дальше',
    'дальше',
    'подробнее',
    'расскажи подробнее',
    'как исправить',
    'что с этим делать',
)


def _line_items(title, items, empty, *, limit=6):
    if not items:
        return f'**{title}:** {empty}'
    body = '\n'.join(f'- {item}' for item in items[:limit])
    return f'**{title}:**\n{body}'


def _stable_choice(options, seed):
    if not options:
        return ''
    digest = hashlib.sha1(str(seed).encode('utf-8')).hexdigest()
    return options[int(digest[:8], 16) % len(options)]


def _clean_list(items):
    if not items:
        return []
    if isinstance(items, str):
        return [items]
    result = []
    for item in items:
        if item is None:
            continue
        result.append(str(item))
    return result


def _estimate_tokens(value):
    """Small local token estimate for demo self-hosted mode.

    It is intentionally approximate: enough to make the UI counter active when
    no external LLM returns real billing usage.
    """
    if value is None:
        return 0
    if isinstance(value, (dict, list, tuple)):
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError, ValueError:
            text = repr(value)
    else:
        text = str(value)
    text = text.strip()
    if not text:
        return 0
    word_count = len(text.split())
    char_estimate = len(text) / 4.0
    word_estimate = word_count * 1.25
    return max(1, int(max(char_estimate, word_estimate)))


def _estimated_usage(message, reply, review, scheme_data, retrieval_context=None):
    compact_context = {
        'score': review.get('score'),
        'status': review.get('status'),
        'summary': review.get('summary'),
        'errors': (review.get('errors') or [])[:6],
        'warnings': (review.get('warnings') or [])[:6],
        'recommendations': (review.get('recommendations') or [])[:8],
        'metrics': review.get('metrics') or {},
        'components': (scheme_data.get('components') or [])[:20] if isinstance(scheme_data, dict) else [],
        'connections_count': len(scheme_data.get('connections') or [])
        if isinstance(scheme_data, dict)
        else 0,
        'retrieval': {
            'sources': (retrieval_context or {}).get('sources') or [],
            'items': ((retrieval_context or {}).get('items') or [])[:4],
        },
    }
    return {
        'input_tokens': _estimate_tokens(message) + _estimate_tokens(compact_context),
        'cache_read_input_tokens': 0,
        'output_tokens': _estimate_tokens(reply),
        'estimated': True,
        'backend': 'self_hosted_rule_ai',
    }


def _deep_hint_for_scheme(scheme_data):
    """Optional PyTorch hint. Never final verdict, never required for chat."""
    if not isinstance(scheme_data, dict) or not scheme_data.get('components'):
        return {'available': False, 'reason': 'empty_scheme'}
    if os.getenv('LOCAL_AI_TORCH_INLINE') != '1':
        try:
            from Dolg_APP.ml.neural import teacher_baseline

            baseline = teacher_baseline(scheme_data)
        except Exception as exc:
            return {'available': False, 'reason': str(exc)[:180]}
        return {
            'available': True,
            'backend': 'teacher_baseline',
            'topology': baseline.get('topology'),
            'topology_confidence': 1.0,
            'risk_score': baseline.get('risk_score'),
            'risk_label': baseline.get('risk_label'),
            'risk_band': baseline.get('risk_band'),
            'next_components': [
                {
                    'component_type': baseline.get('next_component'),
                    'reason': ', '.join(map(str, (baseline.get('risk_reasons') or [])[:4])),
                    'confidence': 0.65,
                }
            ],
            'evidence_sources': ['local_teacher_baseline'],
            'verdict_policy': 'fast rule baseline; set LOCAL_AI_TORCH_INLINE=1 for PyTorch',
        }
    try:
        from Dolg_APP.ml.neural import NeuralCircuitAdvisor, torch_available

        if not torch_available():
            return {'available': False, 'reason': 'torch_unavailable'}
        advisor = NeuralCircuitAdvisor()
        prediction = advisor.predict(scheme_data)
        try:
            from Dolg_APP.services.ai_training import find_similar_training_examples

            prediction['similar_cases'] = find_similar_training_examples(scheme_data, limit=3)
        except Exception:
            prediction['similar_cases'] = []
        prediction['available'] = True
        prediction['verdict_policy'] = 'expert_rules_plus_human_final_control'
        return prediction
    except Exception as exc:
        return {'available': False, 'reason': str(exc)[:180]}


def _deep_hint_section(deep_hint):
    if not deep_hint or not deep_hint.get('available'):
        return ''
    topology_confidence = float(deep_hint.get('topology_confidence') or 0)
    risk_score = float(deep_hint.get('risk_score') or 0)
    lines = [
        f'топология: {deep_hint.get("topology")} ({topology_confidence:.2f})',
        f'риск: {deep_hint.get("risk_label")} / {risk_score:.2f}',
    ]
    baseline = deep_hint.get('expert_baseline') or {}
    if baseline:
        lines.append(
            f'expert baseline: {baseline.get("topology")} / '
            f'{baseline.get("risk_label")} / next={baseline.get("next_component")}'
        )
    if deep_hint.get('agreement_score') is not None:
        lines.append(
            f'baseline agreement: {float(deep_hint.get("agreement_score") or 0):.2f}, '
            f'policy={deep_hint.get("confidence_policy")}'
        )
    next_components = deep_hint.get('next_components') or []
    if next_components:
        best = next_components[0]
        confidence = float(best.get('confidence') or 0)
        lines.append(f'следующий шаг: {best.get("component_type")} ({confidence:.2f})')
    if deep_hint.get('evidence_sources'):
        lines.append('источники примеров: ' + ', '.join(deep_hint['evidence_sources'][:4]))
    lines.append('нейронка дает подсказку, окончательный вывод остается за expert review и человеком')
    similar = deep_hint.get('similar_cases') or []
    if similar:
        case = similar[0]
        lines.append(
            f'similar case #{case.get("id")}: '
            f'{case.get("evidence_kind") or case.get("kind")} ({float(case.get("score") or 0):.2f})'
        )
    return _line_items('PyTorch deep-hint', lines, '', limit=8)


def _history_tail(history, limit=20):
    if not isinstance(history, list):
        return []
    clean = []
    for item in history[-limit:]:
        if not isinstance(item, dict):
            continue
        role = item.get('role')
        content = str(item.get('content') or '').strip()
        if role in {'user', 'assistant'} and content:
            clean.append({'role': role, 'content': content[:2000]})
    return clean


def _last_user_message(history):
    for item in reversed(history or []):
        if item.get('role') == 'user':
            return item.get('content') or ''
    return ''


def _looks_like_followup(text):
    compact = str(text or '').strip().lower()
    if not compact:
        return False
    if any(marker in compact for marker in FOLLOWUP_MARKERS):
        return True
    return len(compact.split()) <= 4 and compact in {'почему', 'зачем', 'дальше', 'подробнее', 'и что'}


def _make_session_summary(previous_summary, history, intent, context_sources):
    chunks = []
    previous_summary = str(previous_summary or '').strip()
    if previous_summary:
        chunks.append(previous_summary[:500])
    last_user = _last_user_message(history)
    if last_user:
        chunks.append(f'Последний вопрос: {last_user[:180]}')
    chunks.append(f'Последний intent: {intent}')
    if context_sources:
        chunks.append('Источники: ' + ', '.join(context_sources[:6]))
    text = ' | '.join(part for part in chunks if part)
    return text[:900]


def _context_sources_for_intent(intent, review):
    sections = review.get('sections') or {}
    sources = ['review']
    if sections.get('connectivity'):
        sources.append('scheme_graph')
    if sections.get('expert_system') or review.get('expert_findings'):
        sources.append('expert_trace')
    if sections.get('external_cad'):
        sources.append('artifact_memory')
        sources.append('external_cad_review')
    if intent in {'measurement', 'scheme_overview', 'demo_script'}:
        sources.append('measurements')
    if intent in {'bom', 'recommend', 'compare'}:
        sources.append('bom_catalog')
    if intent in {'formula', 'recommend', 'compare'}:
        sources.append('engineering_formula')
    if intent in {'learning', 'create_task'}:
        sources.append('learning_by_review')
    if intent == 'import':
        sources.append('cad_import')
    return list(dict.fromkeys(sources))


def _legal_source_items_from_retrieval(retrieval_context):
    return [
        item
        for item in ((retrieval_context or {}).get('items') or [])
        if item.get('source') == 'legal_source'
    ]


def _evidence_lines(review, retrieval_context):
    lines = ['review: score/status, DRC/ERC, BOM и рекомендации текущей схемы']
    if (review.get('sections') or {}).get('expert_system') or review.get('expert_findings'):
        lines.append('expert_trace: rule_id, severity, evidence и recommendation')
    for item in _legal_source_items_from_retrieval(retrieval_context)[:3]:
        title = item.get('title') or item.get('source_id') or 'legal source'
        url = item.get('url') or ''
        lines.append(f'legal_source:{item.get("source_id") or item.get("id")} — {title} ({url})')
    return lines


def _retrieval_context_source_labels(retrieval_context):
    labels = []
    source_labels = {
        'article': 'knowledge_base',
        'learning': 'learning_practice',
        'catalog': 'catalog_snapshot',
        'artifact': 'artifact_memory',
        'training_example': 'ai_memory',
    }
    for source in (retrieval_context or {}).get('sources') or []:
        if source == 'legal_source':
            continue
        labels.append(source_labels.get(source, source))
    for item in _legal_source_items_from_retrieval(retrieval_context)[:4]:
        source_id = item.get('source_id') or item.get('id') or 'source'
        title = item.get('title') or source_id
        url = item.get('url') or ''
        labels.append(f'legal_source:{source_id} — {title} — {url}')
    return labels


def _as_scheme_data(project=None, scheme=None, review=None):
    if isinstance(scheme, dict):
        return scheme
    if project is not None and isinstance(getattr(project, 'scheme_data', None), dict):
        return project.scheme_data
    if isinstance(review, dict) and isinstance(review.get('scheme_data'), dict):
        return review.get('scheme_data')
    return {}


def _component_label(component):
    return str(
        component.get('label')
        or component.get('ref')
        or component.get('part_number')
        or component.get('id')
        or component.get('type')
        or 'component'
    )


def _component_type(component):
    raw = str(component.get('type') or '').strip().lower()
    aliases = {
        'r': 'resistor',
        'res': 'resistor',
        'c': 'capacitor',
        'cap': 'capacitor',
        'v': 'battery',
        'source': 'battery',
        'vsource': 'battery',
        'gnd': 'ground',
        'q': 'transistor',
        'u': 'ic',
    }
    if raw in aliases:
        return aliases[raw]
    if raw.startswith('res'):
        return 'resistor'
    if raw.startswith('cap'):
        return 'capacitor'
    if raw.startswith('bat'):
        return 'battery'
    return raw or 'unknown'


def _scheme_inventory(scheme_data, connectivity):
    components = [item for item in (scheme_data.get('components') or []) if isinstance(item, dict)]
    connections = [item for item in (scheme_data.get('connections') or []) if isinstance(item, dict)]
    counts = Counter(_component_type(item) for item in components)
    if not counts and isinstance(connectivity.get('component_counts'), dict):
        counts.update(connectivity.get('component_counts'))

    parts = []
    for ctype, amount in counts.most_common(8):
        label = TYPE_LABELS_RU.get(ctype, ctype)
        parts.append(f'{label}: {amount}')

    named = [
        _component_label(item)
        for item in components
        if _component_label(item).lower() not in {'component', 'unknown'}
    ][:8]

    return {
        'component_count': len(components) or connectivity.get('component_count', 0),
        'connection_count': len(connections) or connectivity.get('connection_count', 0),
        'counts': parts,
        'labels': named,
    }


def _detect_intent(text, mode, *, history=None, session_summary='', last_intent=None):
    compact = text.lower()
    if _looks_like_followup(compact) and last_intent:
        return last_intent
    if _looks_like_followup(compact) and session_summary:
        for intent in INTENT_LABELS_RU:
            if intent in session_summary:
                return intent
    if _looks_like_followup(compact):
        prev = _last_user_message(history)
        if prev:
            for intent, keywords in KEYWORD_INTENTS:
                if any(keyword in prev.lower() for keyword in keywords):
                    return intent
    if mode == 'recommend':
        explicit_measurement = (
            'измер',
            'осцилл',
            'мультим',
            'probe',
            'пробник',
            'expected',
            'measured',
            'rms',
            'duty',
            'симуляц',
        )
        for intent, keywords in KEYWORD_INTENTS:
            if intent == 'measurement':
                if any(keyword in compact for keyword in explicit_measurement):
                    return 'measurement'
                continue
            if intent == 'recommend':
                continue
            if any(keyword in compact for keyword in keywords):
                return intent
        return 'recommend'
    for intent, keywords in KEYWORD_INTENTS:
        if any(keyword in compact for keyword in keywords):
            return intent
    if mode == 'replace':
        return 'bom'
    if mode == 'explain':
        if any(word in compact for word in ('что делает', 'объясни схему', 'суть', 'кратко')):
            return 'scheme_overview'
        return 'fix_plan'
    return 'overview'


def _opening(intent, message, score, status):
    options = OPENINGS.get(intent) or OPENINGS['overview']
    return _stable_choice(options, f'{intent}|{message}|{score}|{status}').format(
        score=score,
        status=status,
    )


def _graph_summary(connectivity):
    topology = connectivity.get('topology', 'generic')
    return (
        f'Топология: {topology_label_ru(topology)}; '
        f'связных частей: {connectivity.get("connected_components_count", 0)}; '
        f'плавающих фрагментов: {len(connectivity.get("floating_components") or [])}; '
        f'циклов: {connectivity.get("cycle_count", 0)}.'
    )


def _passport_lines(scheme_data, connectivity):
    inventory = _scheme_inventory(scheme_data, connectivity)
    lines = [
        f'компоненты: {inventory["component_count"]}; соединения: {inventory["connection_count"]}',
    ]
    if inventory['counts']:
        lines.append('состав: ' + ', '.join(inventory['counts']))
    if inventory['labels']:
        lines.append('ключевые обозначения: ' + ', '.join(inventory['labels']))
    if connectivity.get('has_output_node'):
        lines.append('выходной узел подписан: ' + ', '.join(map(str, connectivity.get('output_nodes') or [])))
    return lines


def _expert_lines(review):
    expert_section = (review.get('sections') or {}).get('expert_system') or {}
    expert_findings = expert_section.get('findings') or review.get('expert_findings') or []
    lines = []
    for item in expert_findings[:8]:
        translated = translate_finding(item)
        rule_id = translated.get('rule_id') or translated.get('id') or 'rule'
        severity = translated.get('severity_label') or translated.get('severity') or 'info'
        title = translated.get('title') or rule_id
        recommendation = translated.get('recommendation') or ''
        line = f'{rule_id} [{severity}]: {title}'
        if recommendation:
            line += f' -> {recommendation}'
        lines.append(line)
    return lines


def _fault_lines(review):
    lines = []
    for item in review.get('faults') or []:
        title = translate_review_text(item.get('title') or item.get('code') or 'fault')
        symptom = translate_review_text(item.get('symptom') or '')
        recommendation = translate_review_text(item.get('recommendation') or '')
        if symptom and recommendation:
            lines.append(f'{title}: симптом - {symptom}; действие - {recommendation}')
        elif recommendation:
            lines.append(f'{title}: {recommendation}')
        else:
            lines.append(str(title))
    return lines


def _derating_lines(review):
    derating = (review.get('sections') or {}).get('derating') or {}
    lines = []
    for item in derating.get('issues') or []:
        component = item.get('component') or 'component'
        message = translate_review_text(item.get('message') or '')
        level = translate_review_text(item.get('level') or '')
        if message:
            lines.append(f'{component}: {message} ({level})')
    return lines


def _measurement_lines(review):
    rows = build_measurement_rows(review.get('sections') or {})
    lines = [f'{row.get("label")}: {row.get("value")} - {row.get("status")}' for row in rows[:8]]
    latest = (review.get('sections') or {}).get('latest_simulation') or {}
    if not lines and latest:
        analyses = ', '.join(str(key).upper() for key in latest.keys())
        lines.append(f'есть сохраненные результаты симуляции: {analyses}')
    return lines


def _measurement_plan(connectivity):
    topology = connectivity.get('topology')
    if topology == 'voltage_divider':
        return [
            'DC: измерить Vout в средней точке делителя и сравнить с расчетом Vin * R2 / (R1 + R2).',
            'Ток: проверить ток через оба резистора, он должен быть одинаковым без нагрузки.',
            'Нагрузка: подключить тестовую нагрузку и посмотреть, насколько проседает Vout.',
        ]
    if topology == 'rc_network':
        return [
            'AC: найти частоту, где амплитуда падает примерно на 3 дБ.',
            'TRAN: подать ступеньку и оценить постоянную времени tau = R*C.',
            'DC: проверить, что конденсатор не разрывает нужный путь постоянного тока.',
        ]
    if topology == 'led_indicator':
        return [
            'DC: измерить ток ветви LED и сравнить с безопасным диапазоном.',
            'Мощность: проверить P на резисторе, особенно если питание 9-12 В.',
            'Полярность: убедиться, что анод/катод LED подключены правильно.',
        ]
    return [
        'DC: сохранить напряжения ключевых узлов относительно GND.',
        'Ток: проверить токи ветвей у источника и нагруженных компонентов.',
        'TRAN/AC: запускать только после того, как DRC/ERC не показывает критичных ошибок.',
    ]


def _gnd_lines(connectivity):
    paths = connectivity.get('paths_to_ground') or {}
    floating = connectivity.get('floating_components') or []
    if not connectivity.get('has_ground'):
        return [
            'GND не найден: рабочая точка может плавать, а SPICE часто не сходится.',
            'Добавьте опорный узел и подключите к нему обратный путь источника.',
        ]
    missing_paths = [node for node, path in paths.items() if not path and node not in floating][:8]
    lines = ['GND есть: можно строить рабочую точку DC относительно опорного узла.']
    if floating:
        lines.append('Но есть floating-фрагменты: ' + ', '.join(map(str, floating[:8])))
    if missing_paths:
        lines.append('Нет пути до GND у узлов/компонентов: ' + ', '.join(map(str, missing_paths)))
    if not floating and not missing_paths:
        lines.append('Основные компоненты имеют путь до GND.')
    return lines


def _bom_lines(review, catalog):
    bom = (review.get('sections') or {}).get('bom') or {}
    lines = [
        f'связано с каталогом: {bom.get("matched_count", 0)}',
        f'без связи с каталогом: {bom.get("missing_catalog_count", 0)}',
    ]
    for item in (bom.get('risks') or [])[:6]:
        component = item.get('component') or 'component'
        message = translate_review_text(item.get('message') or '')
        if message:
            lines.append(f'{component}: {message}')
    if catalog:
        lines.append(f'в текущем snapshot каталога доступно позиций для подсказок: {len(catalog)}')
    return lines


def _import_lines(review):
    import_summary = (review.get('sections') or {}).get('import') or review.get('import_summary') or {}
    lines = []
    if not import_summary:
        return lines
    if import_summary.get('format'):
        lines.append(f'формат: {import_summary.get("format")}')
    unsupported = import_summary.get('unsupported') or import_summary.get('unsupported_items') or []
    warnings = import_summary.get('warnings') or []
    if unsupported:
        lines.append('неподдержанные элементы: ' + ', '.join(map(str, unsupported[:8])))
    if warnings:
        lines.extend(translate_review_text(warnings[:6]))
    return lines


def _artifact_lines(review):
    external = (review.get('sections') or {}).get('external_cad') or {}
    training = artifact_training_summary((review.get('sections') or {}).get('artifacts') or [])
    lines = []
    if external:
        lines.append(
            f'artifacts: {external.get("artifact_count", 0)}, '
            f'CAD findings: {external.get("finding_count", 0)}, '
            f'unsupported: {external.get("unsupported_count", 0)}'
        )
        for item in (external.get('findings') or [])[:5]:
            title = translate_review_text(item.get('title') or item.get('rule_id') or 'finding')
            source = item.get('source_name') or 'artifact'
            recommendation = translate_review_text(item.get('recommendation') or '')
            line = f'{source}: {title}'
            if recommendation:
                line += f' -> {recommendation}'
            lines.append(line)
    if training.get('artifact_count'):
        lines.append(
            f'AI memory corpus: {training.get("artifact_count")} artifacts, '
            f'{training.get("check_findings")} check findings, '
            f'{training.get("fault_cases")} fault cases.'
        )
    return lines


def _artifact_learning_lines(review):
    suggestions = learning_suggestions_from_artifacts((review.get('sections') or {}).get('artifacts') or [])
    return [
        f'{item.get("task_type")}: {item.get("title")} ({item.get("rubric", {}).get("source_artifact", "")})'
        for item in suggestions[:5]
    ]


def _recommendation_lines(review, catalog):
    recs = _clean_list(translate_review_text(review.get('recommendations') or []))
    if catalog:
        recs.append(f'Если нужен подбор из ассортимента, в snapshot каталога есть {len(catalog)} позиций.')
    if not recs:
        recs.append('Сначала задайте целевое напряжение/ток, затем проверьте мощность, корпус и наличие.')
    return recs


def _quick_actions(intent, connectivity):
    base = {
        'gnd': [
            ('Добавить GND', 'Почему нужен GND и куда его подключить?', 'explain', 'prompt'),
            ('Запустить DC', 'Что проверить в DC после добавления GND?', 'explain', 'prompt'),
            ('Floating-фрагменты', 'Проверь floating-фрагменты и пути до GND', 'explain', 'prompt'),
        ],
        'measurement': [
            (
                'Что измерить?',
                'Что измерить дальше и как сравнить expected vs measured?',
                'explain',
                'prompt',
            ),
            ('Vout', 'Как проверить Vout и допуск измерения?', 'explain', 'prompt'),
            ('AC/TRAN', 'Какие AC/TRAN метрики стоит сохранить?', 'explain', 'prompt'),
        ],
        'thermal': [
            ('Проверить мощность', 'Проверь мощность и тепловой запас компонентов', 'explain', 'prompt'),
            ('Увеличить запас', 'Как увеличить запас по мощности и температуре?', 'recommend', 'prompt'),
            ('Другой корпус', 'Какой корпус или номинал выбрать для запаса?', 'recommend', 'prompt'),
        ],
        'bom': [
            ('Связать BOM', 'Что не связано с каталогом и как это исправить?', 'replace', 'prompt'),
            ('SPICE/CAD flags', 'Проверь datasheet, SPICE и CAD flags для BOM', 'replace', 'prompt'),
            ('Экспорт BOM', 'Что проверить перед экспортом BOM и заказом?', 'replace', 'prompt'),
        ],
        'learning': [
            ('Задание из ошибки', 'Создай учебное задание из этой ошибки', 'explain', 'prompt'),
            ('Исправить схему', 'Составь практикум: найти ошибку и исправить схему', 'explain', 'prompt'),
            ('Подтвердить измерением', 'Как подтвердить исправление измерением?', 'explain', 'prompt'),
        ],
        'create_task': [
            ('Math task', 'Сделай числовое задание по этой схеме', 'explain', 'prompt'),
            ('Circuit build', 'Сделай задание на сборку схемы по этой ошибке', 'explain', 'prompt'),
            ('Simulation measure', 'Сделай задание на измерение результата симуляции', 'explain', 'prompt'),
        ],
        'import': [
            ('Import preview', 'Что проверить в import preview?', 'explain', 'prompt'),
            ('Unsupported', 'Объясни unsupported элементы импорта', 'explain', 'prompt'),
            ('Review import', 'Как запустить review после импорта?', 'explain', 'prompt'),
        ],
        'recommend': [
            ('Уточнить параметры', 'Уточни Vin, Vout, ток нагрузки и допуск', 'recommend', 'prompt'),
            ('Проверить номинал', 'Подбери номинал и проверь мощность', 'recommend', 'prompt'),
            ('Проверить запас', 'Проверь запас по напряжению, току и мощности', 'recommend', 'prompt'),
        ],
        'fix_plan': [
            ('Критичные ошибки', 'Найди критичные ошибки и дай план исправления', 'explain', 'prompt'),
            ('Запустить симуляцию', 'Что запустить после исправления ошибок?', 'explain', 'prompt'),
            ('Сохранить review', 'Что должно быть в финальном review?', 'explain', 'prompt'),
        ],
        'why_failed': [
            ('Причина сбоя', 'Почему проверка не проходит?', 'explain', 'prompt'),
            ('DRC/ERC', 'Разбери ошибки DRC и ERC', 'explain', 'prompt'),
            ('План фикса', 'Составь короткий план исправления', 'explain', 'prompt'),
        ],
        'formula': [
            ('Формула', 'Покажи формулу и расчет по этой схеме', 'recommend', 'prompt'),
            ('Проверить единицы', 'Проверь единицы измерения и порядок величин', 'recommend', 'prompt'),
            ('Сравнить с измерением', 'Сравни расчет с измерением', 'explain', 'prompt'),
        ],
        'compare': [
            ('Сравнить номиналы', 'Сравни варианты номиналов для этой схемы', 'recommend', 'prompt'),
            ('BOM-риск', 'Сравни варианты по BOM и доступности', 'replace', 'prompt'),
            ('Инженерный запас', 'Сравни варианты по запасу', 'recommend', 'prompt'),
        ],
        'demo_script': [
            ('Речь 30 секунд', 'Как объяснить эту схему на защите за 30 секунд?', 'explain', 'prompt'),
            ('Вопросы комиссии', 'Какие вопросы могут задать по этой схеме?', 'explain', 'prompt'),
            ('Демо маршрут', 'Как показать эту схему в демо?', 'explain', 'prompt'),
        ],
        'scheme_overview': [
            ('Разобрать схему', 'Что делает эта схема за 30 секунд?', 'explain', 'prompt'),
            ('Найти ошибки', 'Есть ли в схеме критичные ошибки?', 'explain', 'prompt'),
            ('Что измерить?', 'Что измерить в этой схеме?', 'explain', 'prompt'),
        ],
        'overview': [
            ('Разобрать схему', 'Что делает эта схема за 30 секунд?', 'explain', 'prompt'),
            ('Запустить DRC++', 'Найди ошибки и аномалии схемы', 'explain', 'prompt'),
            ('Сохранить измерения', 'Какие измерения сохранить?', 'explain', 'prompt'),
        ],
    }
    actions = list(base.get(intent) or base['overview'])
    if connectivity.get('topology') == 'voltage_divider':
        actions.append(
            (
                'Измерить Vout делителя',
                'Как измерить Vout делителя и сравнить с расчетом?',
                'explain',
                'prompt',
            )
        )
    elif connectivity.get('topology') == 'rc_network':
        actions.append(('Найти -3 дБ точку', 'Как найти -3 дБ точку RC-цепи?', 'explain', 'prompt'))
    elif connectivity.get('topology') == 'led_indicator':
        actions.append(
            ('Измерить ток LED', 'Как измерить ток LED и проверить резистор?', 'explain', 'prompt')
        )

    # Prompt-actions (reask AI) — старый формат с tuple, поддерживается фронтом.
    prompt_actions = [
        {'label': label, 'prompt': prompt, 'mode': mode, 'action_type': action_type, 'kind': 'prompt'}
        for label, prompt, mode, action_type in actions[:5]
    ]
    # Tool-actions — новый формат с функцией: AI предлагает что-то «нажать»
    # в симуляторе/CAD. Фронт через whitelist (Dolg_APP/services/ai_tools.py)
    # выполнит ровно перечисленное и ничего больше.
    tool_actions = _tool_actions_for_intent(intent, connectivity)
    return prompt_actions + tool_actions


def _skill_manifest(intent):
    """Structured assistant capabilities for UI buttons and documentation."""
    skills = [
        ('diagnose_scheme', 'Найти ошибку', 'Проверить DRC/ERC, GND, связи и findings', 'fix_plan'),
        ('explain_review', 'Объяснить review', 'Пояснить rule_id, evidence и recommendation', 'why_failed'),
        (
            'suggest_measurement',
            'Что измерить',
            'Подобрать следующую метрику expected vs measured',
            'measurement',
        ),
        ('choose_nominal', 'Подобрать номинал', 'Использовать формулы, ограничения и BOM', 'recommend'),
        ('compare_variants', 'Сравнить варианты', 'Сравнить электрический результат, запас и BOM', 'compare'),
        (
            'learning_task_from_error',
            'Сделать задание',
            'Собрать практическое задание из ошибки',
            'create_task',
        ),
        ('artifact_summary', 'Разобрать артефакт', 'Объяснить импортированный отчет или CAD-файл', 'import'),
        (
            'defense_demo_script',
            'Речь для защиты',
            'Собрать демонстрационный рассказ по схеме',
            'demo_script',
        ),
    ]
    return [
        {
            'key': key,
            'label': label,
            'description': description,
            'intent': mapped_intent,
            'active': mapped_intent == intent,
        }
        for key, label, description, mapped_intent in skills
    ]


def _tool_actions_for_intent(intent, connectivity):
    """Build tool-actions based on detected intent + scheme state.

    Это «руки» AI: вместо переспрашивания prompt'ом — кнопка нажимает реальную
    функцию симулятора/CAD. Состав tool-actions подобран так, чтобы пользователь
    мог одним кликом продолжить работу (запустить симуляцию, добавить GND,
    открыть 3D, экспортнуть BOM и т.д.).
    """
    try:
        from Dolg_APP.services.ai_tools import build_tool_action
    except ImportError:
        return []

    out = []
    has_ground = bool((connectivity or {}).get('has_ground'))
    has_source = bool((connectivity or {}).get('has_source'))
    topology = (connectivity or {}).get('topology', 'generic')
    component_count = int((connectivity or {}).get('component_count') or 0)

    # GND intent или явно нет GND → предложить добавить GND.
    if intent == 'gnd' or not has_ground:
        act = build_tool_action('scheme.add_component', {'type': 'ground'}, override_label='Добавить GND')
        if act:
            out.append(act)

    # Measurement intent или вообще ничего не симулировали → запуск DC + 3D-thermal
    if intent in {'measurement', 'thermal', 'scheme_overview'} and component_count >= 2:
        if has_source and has_ground:
            act = build_tool_action('simulation.run_dc', override_label='▶️ Запустить DC')
            if act:
                out.append(act)
        if topology == 'rc_network' or intent == 'thermal':
            act = build_tool_action(
                'simulation.run_tran', {'duration_ms': 50}, override_label='📈 Запустить TRAN 50 мс'
            )
            if act:
                out.append(act)
        if intent == 'thermal':
            act = build_tool_action('view.toggle_thermal_3d', override_label='🌡 Тепловая карта в 3D')
            if act:
                out.append(act)

    # Если RC/LC топология → AC анализ
    if topology in {'rc_network', 'lc_tank'} and intent in {'formula', 'measurement', 'scheme_overview'}:
        act = build_tool_action(
            'simulation.run_ac', {'f_start': 10, 'f_stop': 1000000}, override_label='📊 АЧХ (10 Гц … 1 МГц)'
        )
        if act:
            out.append(act)

    # BOM intent → экспорт BOM
    if intent == 'bom':
        act = build_tool_action('export.bom', override_label='📋 Экспорт BOM')
        if act:
            out.append(act)

    # Demo/explain → открыть 3D
    if intent in {'demo_script', 'scheme_overview'} and component_count >= 3:
        act = build_tool_action('view.show_3d', override_label='🎬 Открыть 3D')
        if act:
            out.append(act)

    # Fix plan / why_failed → запустить DRC
    if intent in {'fix_plan', 'why_failed'}:
        act = build_tool_action('pipeline.run_drc', override_label='✓ Запустить DRC')
        if act:
            out.append(act)
        act = build_tool_action('pipeline.run_review', override_label='🧠 Engineering Review')
        if act:
            out.append(act)

    # Limit — максимум 3 tool-actions чтобы UI не забивался.
    return out[:3]


def _confidence(review):
    metrics = review.get('metrics') or {}
    evidence = 0
    evidence += 1 if metrics.get('components') else 0
    evidence += 1 if metrics.get('connections') else 0
    evidence += 1 if metrics.get('expert_findings') is not None else 0
    evidence += 1 if metrics.get('measurements') else 0
    evidence += 1 if metrics.get('simulations') else 0
    if evidence >= 4:
        return 0.86
    if evidence >= 2:
        return 0.72
    return 0.55


def _compose_reply(intent, message, review, scheme_data, catalog, retrieval_context=None):
    status = review.get('status_label') or review.get('status')
    score = review.get('score')
    summary = translate_review_text(review.get('summary', ''))
    connectivity = (review.get('sections') or {}).get('connectivity') or {}
    expert_lines = _expert_lines(review)
    warnings = _clean_list(translate_review_text(review.get('warnings') or []))
    errors = _clean_list(translate_review_text(review.get('errors') or []))
    recs = _recommendation_lines(review, catalog)

    common_head = [
        _opening(intent, message, score, status),
        summary,
        _graph_summary(connectivity),
    ]

    # L2 + Plan-then-Execute: планировщик выбирает движки (для обзорных/диагностических
    # запросов — несколько сразу), исполнитель = реестр. Для узких запросов план = [intent]
    # (обратная совместимость). Числа — из движков (compute-don't-guess).
    topology = connectivity.get('topology')
    plan = ai_algorithms.plan_for(message, intent)
    plan_sections = ai_algorithms.sections_for_plan(plan, scheme_data, topology)
    engine_sections = []
    if len(plan) > 1 and len(plan_sections) > 1:
        # Видимый план (ReAct-трассируемость): какие проверки агент прогнал.
        engine_sections.append(
            _line_items(
                'План проверки (агент)',
                [f'{i + 1}. {title}' for i, (title, _) in enumerate(plan_sections)],
                '',
            )
        )
    engine_sections += [_line_items(title, lines, '') for title, lines in plan_sections]

    if intent in {'overview', 'scheme_overview'}:
        sections = [
            *common_head,
            *engine_sections,
            _line_items('Паспорт схемы', _passport_lines(scheme_data, connectivity), 'Схема пока пустая.'),
            _line_items('Экспертный след', expert_lines, 'Экспертные правила не нашли отдельного риска.'),
            _line_items('Следующие действия', recs, 'Откройте отчет review для деталей.'),
        ]
    elif intent == 'why_failed':
        failure_lines = []
        failure_lines.extend(errors)
        failure_lines.extend(warnings[:4])
        failure_lines.extend(_expert_lines(review)[:4])
        if not failure_lines:
            failure_lines = [
                'Явной причины падения в review нет: проверьте входные данные запроса, GND и сохраненные результаты симуляции.'
            ]
        sections = [
            *common_head,
            *engine_sections,
            _line_items('Почему может не проходить', failure_lines, 'Критичных причин не найдено.'),
            _line_items(
                'План проверки',
                [
                    'сначала исправить DRC/ERC ошибки',
                    'проверить GND, источник и floating-фрагменты',
                    'после этого запустить DC и сохранить expected vs measured',
                ],
                'Начните с review.',
            ),
        ]
    elif intent == 'gnd':
        sections = [
            *common_head,
            _line_items('GND и опорная точка', _gnd_lines(connectivity), 'Данных по GND нет.'),
            _line_items('Ошибки', errors, 'Критичных DRC/ERC-ошибок нет.'),
            _line_items('Следующие действия', recs, 'После GND сохраните DC-измерения.'),
        ]
    elif intent == 'measurement':
        sections = [
            *common_head,
            *engine_sections,
            _line_items('Сохраненные измерения', _measurement_lines(review), 'Измерений пока нет.'),
            _line_items(
                'Что измерить дальше', _measurement_plan(connectivity), 'Начните с DC-напряжений узлов.'
            ),
            _line_items('Предупреждения', warnings, 'Предупреждений по review нет.'),
        ]
    elif intent == 'thermal':
        sections = [
            *common_head,
            *engine_sections,
            _line_items(
                'Запас по мощности и температуре',
                _derating_lines(review),
                'По доступным данным перегрузки не обнаружены.',
            ),
            _line_items(
                'Что проверить',
                [
                    'сравнить мощность элемента с допустимой мощностью корпуса',
                    'для стабилизатора оценить падение напряжения и рассеиваемую мощность',
                    'если запас меньше 30%, выбрать номинал/корпус с запасом',
                ],
                'Derating-данных недостаточно.',
            ),
        ]
    elif intent == 'bom':
        sections = [
            *common_head,
            _line_items('BOM и каталог', _bom_lines(review, catalog), 'BOM-риски не найдены.'),
            _line_items(
                'Следующие действия',
                [
                    'связать элементы схемы с товарами каталога',
                    'проверить datasheet, SPICE/CAD flags и lifecycle',
                    'после review экспортировать BOM или сформировать заказ',
                ],
                'BOM можно собирать после связи компонентов.',
            ),
        ]
    elif intent in {'learning', 'create_task'}:
        learning_plan = []
        for item in (review.get('faults') or [])[:4]:
            title = translate_review_text(item.get('title') or item.get('code') or 'ошибка')
            learning_plan.append(f'{title}: найти причину, исправить схему, подтвердить измерением')
        if not learning_plan:
            learning_plan = [
                'дать числовую задачу по расчету ожидаемого значения',
                'дать задание на сборку схемы в CAD',
                'дать задание на измерение результата симуляции',
            ]
        sections = [
            *common_head,
            _line_items('Идея учебного задания', learning_plan, 'Ошибок для задания не найдено.'),
            _line_items(
                'Что проверять', _measurement_plan(connectivity), 'Проверить расчет, схему и измерение.'
            ),
        ]
    elif intent == 'formula':
        if topology == 'voltage_divider':
            formula_lines = [
                'Делитель: Vout = Vin * R2 / (R1 + R2).',
                'После расчета нужно проверить ток через цепочку и влияние нагрузки.',
            ]
        elif topology == 'rc_network':
            formula_lines = [
                'RC cutoff: fc = 1 / (2 * pi * R * C).',
                'Для проверки в AC ищите точку около -3 дБ.',
            ]
        elif topology == 'led_indicator':
            formula_lines = [
                'LED-резистор: R = (Vin - Vf) / Iled.',
                'Мощность резистора: P = Iled^2 * R, корпус брать с запасом.',
            ]
        else:
            formula_lines = [
                'Для резистивной ветви используйте закон Ома: U = I * R.',
                'Для мощности используйте P = U * I или P = I^2 * R.',
            ]
        sections = [
            *common_head,
            *engine_sections,
            _line_items('Формула', formula_lines, 'Недостаточно данных для выбора формулы.'),
            _line_items(
                'Что сверить', _measurement_plan(connectivity), 'Сначала сохраните расчетное expected value.'
            ),
        ]
    elif intent == 'compare':
        sections = [
            *common_head,
            _line_items(
                'Как сравнивать варианты',
                [
                    'электрический результат: напряжение, ток, частота или мощность',
                    'инженерный запас: мощность, температура, напряжение, ток',
                    'BOM: наличие, lifecycle, datasheet, SPICE/CAD-модель',
                    'демо-критерий: вариант должен проходить review и иметь понятное измерение',
                ],
                'Нужно минимум два варианта.',
            ),
            _line_items('Риски текущего варианта', warnings + errors, 'Явных рисков текущего варианта нет.'),
        ]
    elif intent == 'demo_script':
        sections = [
            *common_head,
            _line_items(
                'Как рассказать на защите',
                [
                    'сначала назвать функцию схемы и топологию',
                    'затем показать GND/источник и ключевые элементы',
                    'после этого открыть измерение expected vs measured',
                    'в конце показать review: score, ошибки, рекомендации и BOM',
                ],
                'Сценарий зависит от выбранной схемы.',
            ),
            _line_items(
                'Вопросы комиссии',
                [
                    'почему выбран такой номинал',
                    'что будет при изменении нагрузки',
                    'как проверяется GND и корректность симуляции',
                    'какой запас по мощности и температуре',
                ],
                'Можно подготовить вопросы после выбора схемы.',
            ),
        ]
    elif intent == 'import':
        sections = [
            *common_head,
            _line_items('Import preview', _import_lines(review), 'Этот проект не содержит import-summary.'),
            _line_items(
                'После импорта',
                [
                    'сохранить unsupported элементы как warnings, а не терять их',
                    'нормализовать схему во внутренний scheme_data',
                    'запустить Engineering Review и связать компоненты с BOM',
                ],
                'Запустите review после импорта.',
            ),
        ]
    elif intent == 'recommend':
        sections = [
            *common_head,
            *engine_sections,
            _line_items('Что выбрать или проверить', recs, 'Явных рисков выбора не найдено.'),
            _line_items(
                'Ограничения перед подбором',
                [
                    'задать входное и выходное напряжение или ток нагрузки',
                    'проверить мощность и температурный запас',
                    'сверить корпус, наличие, datasheet и SPICE/CAD-модель',
                ],
                'Нужны целевые параметры.',
            ),
        ]
    else:
        sections = [
            *common_head,
            _line_items('Экспертный след', expert_lines, 'Экспертные правила не нашли отдельного риска.'),
            _line_items('Ошибки', errors, 'Критичных DRC/ERC-ошибок нет.'),
            _line_items(
                'Возможные неисправности', _fault_lines(review), 'Типовой сценарий неисправности не найден.'
            ),
            _line_items('Следующие действия', recs, 'Сохраните симуляцию и сравните измерения.'),
        ]

    retrieval = ai_retrieval_lines(retrieval_context)
    evidence = _evidence_lines(review, retrieval_context)
    if evidence:
        sections.append(_line_items('Опираюсь на', evidence, 'Доступен только review текущего проекта.'))
    if retrieval:
        sections.append(
            _line_items('База DOLG по теме', retrieval, 'Подходящих материалов в локальной базе пока нет.')
        )

    artifact_lines = _artifact_lines(review)
    if artifact_lines:
        sections.append(
            _line_items('Инженерные артефакты', artifact_lines, 'Артефактов в контексте пока нет.')
        )
    if intent in {'learning', 'create_task'}:
        artifact_tasks = _artifact_learning_lines(review)
        if artifact_tasks:
            sections.append(_line_items('Задания из артефактов', artifact_tasks, ''))

    return '\n\n'.join(str(item) for item in sections if item)


def _render_directives(intent, reply, scheme_data):
    """L3 гибрид: структурные render-айтемы (plot/table) + inline-токены из текста.

    Структурный слой надёжен для крупных виджетов; inline-токены [[value:…]] /
    [[highlight:R1]] из прозы — для контекстных вставок (фронт рендерит оба)."""
    items = list(ai_render.build_render_items(scheme_data, intent))
    for token in ai_render.parse_inline_tokens(reply):
        items.append({'type': token['type'], 'arg': token['arg'], 'raw': token['raw'], 'placement': 'inline'})
    return items


def _lightweight_review(scheme_data):
    """Fast inline review for chat payloads without a saved project.

    The full Engineering Review imports heavier expert/fuzzy engines. For the
    floating AI panel we need a sub-second context snapshot first; users can
    still run the full review from the dedicated tool action.
    """
    scheme_data = scheme_data if isinstance(scheme_data, dict) else {}
    components = [item for item in (scheme_data.get('components') or []) if isinstance(item, dict)]
    connections = [item for item in (scheme_data.get('connections') or []) if isinstance(item, dict)]
    try:
        from Dolg_APP.services.schematic_graph import analyze_graph_topology

        graph = analyze_graph_topology(scheme_data)
        connectivity = graph.get('metrics') or {}
        errors = _clean_list(graph.get('errors') or [])
        warnings = _clean_list(graph.get('warnings') or [])
    except Exception:
        counts = Counter(_component_type(item) for item in components)
        connectivity = {
            'topology': 'generic',
            'component_count': len(components),
            'connection_count': len(connections),
            'component_counts': dict(counts),
            'has_ground': bool(counts.get('ground')),
            'has_source': bool(counts.get('battery')),
            'connected_components_count': 0,
            'floating_components': [],
            'cycle_count': 0,
            'paths_to_ground': {},
            'output_nodes': [],
            'has_output_node': False,
        }
        errors = []
        warnings = []

    counts = connectivity.get('component_counts') or Counter(_component_type(item) for item in components)
    if not components:
        warnings.append('Схема пустая: добавьте источник, GND и нагрузку.')
    if len(components) > 1 and not connections:
        warnings.append('Компоненты пока не соединены.')
    if connectivity.get('has_source') and not connectivity.get('has_ground'):
        warnings.append('Есть источник, но нет GND.')
    if not connectivity.get('has_source') and components:
        warnings.append('Не найден источник питания или входной сигнал.')
    if counts.get('led') and not counts.get('resistor'):
        warnings.append('LED без токоограничительного резистора.')

    recommendations = []
    if not components:
        recommendations.extend(
            ['Добавить источник питания.', 'Добавить GND.', 'Добавить нагрузку или тестовый узел.']
        )
    elif connectivity.get('has_source') and not connectivity.get('has_ground'):
        recommendations.append('Подключить общий GND к обратному пути источника.')
    elif len(components) > 1 and not connections:
        recommendations.append('Соединить компоненты в замкнутый путь тока.')
    if counts.get('battery') and counts.get('ground') and not counts.get('capacitor'):
        recommendations.append('Добавить развязывающий конденсатор или RC-фильтр питания.')
    if counts.get('transistor') or counts.get('npn') or counts.get('pnp'):
        recommendations.append('Проверить резистор базы/затвора и защиту нагрузки.')
    recommendations.append('Запустить DRC++ перед симуляцией и сохранить измерения.')

    score = max(35, 100 - len(errors) * 25 - len(warnings) * 10)
    status = 'risk' if errors or len(warnings) >= 3 else 'watch' if warnings else 'ok'
    status_label = {'ok': 'готово', 'watch': 'нужно проверить', 'risk': 'есть риск'}[status]
    summary = f'{len(components)} компонентов, {len(connections)} соединений, {len(errors)} ошибок, {len(warnings)} предупреждений.'
    return {
        'score': score,
        'status': status,
        'status_label': status_label,
        'summary': summary,
        'errors': errors[:8],
        'warnings': warnings[:8],
        'recommendations': recommendations[:8],
        'faults': [],
        'expert_findings': [],
        'sections': {
            'connectivity': connectivity,
            'expert_system': {'findings': []},
            'bom': {},
            'derating': {'issues': []},
            'latest_simulation': {},
            'artifacts': [],
            'external_cad': {},
        },
        'metrics': {
            'components': len(components),
            'connections': len(connections),
            'expert_findings': 0,
            'measurements': 0,
            'simulations': 0,
        },
        'scheme_data': scheme_data,
    }


def build_rule_based_reply(
    message,
    *,
    mode='explain',
    project=None,
    scheme=None,
    review=None,
    catalog=None,
    history=None,
    session_summary='',
    last_intent=None,
    include_deep_hint=False,
):
    """Deterministic project assistant used when no external LLM is configured.

    It intentionally answers from structured project facts only: schematic JSON,
    review sections, DRC/ERC, BOM risks, derating and measurements.
    """
    raw_message = (message or '').strip()
    text = raw_message.lower()
    history_tail = _history_tail(history, limit=20)
    scheme_data = _as_scheme_data(project=project, scheme=scheme, review=review)
    if review is None:
        if project is not None:
            review = build_design_review(
                project,
                simulation_runs=list(project.simulation_runs.all()[:5]),
                measurements=list(project.measurements.all()[:20])
                if hasattr(project, 'measurements')
                else [],
            )
        else:
            review = _lightweight_review(scheme_data)

    intent = _detect_intent(
        text,
        mode,
        history=history_tail,
        session_summary=session_summary,
        last_intent=last_intent,
    )
    retrieval_context = build_retrieval_context(
        raw_message,
        intent=intent,
        project=project,
        scheme=scheme_data,
        review=review,
        limit=6,
    )
    reply_seed = (
        f'{raw_message}|history={len(history_tail)}|last={last_intent or ""}|summary={session_summary[-120:]}'
    )
    reply = _compose_reply(
        intent, reply_seed, review, scheme_data, catalog, retrieval_context=retrieval_context
    )
    deep_hint = _deep_hint_for_scheme(scheme_data) if include_deep_hint else None
    deep_section = _deep_hint_section(deep_hint)
    if deep_section:
        reply = f'{reply}\n\n{deep_section}'
    connectivity = (review.get('sections') or {}).get('connectivity') or {}
    usage = _estimated_usage(raw_message, reply, review, scheme_data, retrieval_context=retrieval_context)
    context_sources = _context_sources_for_intent(intent, review)
    if deep_hint and deep_hint.get('available'):
        context_sources.append('neural_deep_hint')
    for label in _retrieval_context_source_labels(retrieval_context):
        if label not in context_sources:
            context_sources.append(label)
    quick_actions = _quick_actions(intent, connectivity)
    updated_summary = _make_session_summary(session_summary, history_tail, intent, context_sources)
    render = _render_directives(intent, reply, scheme_data)
    return {
        'reply': reply,
        'agent': 'Self AI engineer',
        'intent': intent,
        'intent_label': INTENT_LABELS_RU.get(intent, intent),
        'confidence': _confidence(review),
        'quick_actions': quick_actions,
        'render': render,
        'skills': _skill_manifest(intent),
        'context_sources': context_sources,
        'used_context': {
            'history_messages': len(history_tail),
            'session_summary': bool(session_summary),
            'last_intent': last_intent or '',
            'retrieval_items': len(retrieval_context.get('items') or []),
            'retrieval_sources': retrieval_context.get('sources') or [],
            'deep_hint': bool(deep_hint and deep_hint.get('available')),
        },
        'deep_hint': deep_hint or {'available': False, 'reason': 'not_requested'},
        'session_summary': updated_summary,
        'usage': usage,
        'retrieval_context': retrieval_context,
    }


def build_ai_scheme_context(
    project=None, scheme=None, measurements=None, simulation_runs=None, include_deep_hint=False
):
    """Build compact context card data for the AI panel."""
    scheme_data = _as_scheme_data(project=project, scheme=scheme)
    if project is not None:
        if measurements is None and hasattr(project, 'measurements'):
            measurements = list(project.measurements.all()[:8])
        if simulation_runs is None and hasattr(project, 'simulation_runs'):
            simulation_runs = list(project.simulation_runs.all()[:5])

    if project is None:

        class _InlineProject:
            pass

        inline_project = _InlineProject()
        inline_project.scheme_data = scheme_data
        project_for_review = inline_project
    else:
        project_for_review = project

    review = build_design_review(
        project_for_review,
        simulation_runs=simulation_runs or [],
        measurements=measurements or [],
    )
    sections = review.get('sections') or {}
    connectivity = sections.get('connectivity') or {}
    bom = sections.get('bom') or {}
    validity = sections.get('validity') or {}
    external_cad = sections.get('external_cad') or {}
    artifact_memory = artifact_training_summary(sections.get('artifacts') or [])
    measurement_rows = build_measurement_rows(sections)
    quick_actions = _quick_actions('scheme_overview', connectivity)
    facts = {
        'components': connectivity.get('component_count', 0),
        'connections': connectivity.get('connection_count', 0),
        'has_ground': bool(connectivity.get('has_ground')),
        'has_source': bool(connectivity.get('has_source')),
        'floating_fragments': len(connectivity.get('floating_components') or []),
        'drc_errors': len(review.get('errors') or []),
        'drc_warnings': len(review.get('warnings') or []),
        'bom_matched': bom.get('matched_count', 0),
        'bom_missing': bom.get('missing_catalog_count', 0),
        'validity_issues': len(validity.get('issues') or []),
        'artifact_count': artifact_memory.get('artifact_count', 0),
        'external_cad_findings': external_cad.get('finding_count', 0),
        'fault_cases': artifact_memory.get('fault_cases', 0),
    }
    deep_hint = (
        _deep_hint_for_scheme(scheme_data)
        if include_deep_hint
        else {'available': False, 'reason': 'not_requested'}
    )
    return {
        'summary': review.get('summary', ''),
        'topology': connectivity.get('topology', 'generic'),
        'topology_label': topology_label_ru(connectivity.get('topology', 'generic')),
        'score': review.get('score'),
        'status': review.get('status'),
        'status_label': review.get('status_label') or review.get('status'),
        'facts': facts,
        'warnings': (review.get('warnings') or [])[:6],
        'errors': (review.get('errors') or [])[:6],
        'measurements': measurement_rows[:6],
        'quick_prompts': quick_actions,
        'context_sources': _context_sources_for_intent('scheme_overview', review),
        'deep_hint': deep_hint,
    }
