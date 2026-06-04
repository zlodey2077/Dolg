from django.urls import reverse

RULES = [
    {
        'slug': 'diagnostics-no-ground',
        'reason': 'В review найдена проблема с GND или плавающими узлами.',
        'needles': ('missing gnd', 'missing_ground', 'gnd reference', 'floating'),
        'topologies': (),
    },
    {
        'slug': 'delitel-napryazheniya-praktikum',
        'reason': 'Схема похожа на делитель напряжения: полезно сверить расчет Vout и DC-измерение.',
        'needles': ('voltage divider', 'vout', 'divider'),
        'topologies': ('voltage_divider',),
    },
    {
        'slug': 'rc-filtr-praktikum',
        'reason': 'В проекте есть RC-топология: стоит проверить частоту среза и -3 дБ точку.',
        'needles': ('rc network', 'rc-filter', 'cutoff', '-3'),
        'topologies': ('rc_network',),
    },
    {
        'slug': 'led-indikator-praktikum',
        'reason': 'В проекте есть LED-ветвь: проверьте ток и ограничительный резистор.',
        'needles': ('led', 'diode current'),
        'topologies': ('led_indicator',),
    },
    {
        'slug': 'diagnostics-derating',
        'reason': 'Review указывает на запас по мощности или перегрев.',
        'needles': ('derating', 'overheat', 'thermal', 'power', 'junction', 'перегрев'),
        'topologies': (),
    },
]

FALLBACK_SLUGS = (
    'diagnostics-no-ground',
    'delitel-napryazheniya-praktikum',
    'rc-filtr-praktikum',
)


def _review_payload(review_or_report):
    if isinstance(review_or_report, dict):
        return review_or_report
    return {
        'errors': getattr(review_or_report, 'errors', []) or [],
        'warnings': getattr(review_or_report, 'warnings', []) or [],
        'recommendations': getattr(review_or_report, 'recommendations', []) or [],
        'faults': getattr(review_or_report, 'faults', []) or [],
        'metrics': getattr(review_or_report, 'metrics', {}) or {},
        'sections': getattr(review_or_report, 'sections', {}) or {},
        'import_summary': getattr(review_or_report, 'import_summary', {}) or {},
    }


def _haystack(payload):
    parts = []
    for key in ('errors', 'warnings', 'recommendations', 'faults'):
        value = payload.get(key) or []
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        else:
            parts.append(str(value))
    sections = payload.get('sections') or {}
    if isinstance(sections, dict):
        parts.append(str(sections.get('expert_system') or ''))
        parts.append(str(sections.get('connectivity') or ''))
        parts.append(str(sections.get('derating') or ''))
    parts.append(str(payload.get('import_summary') or ''))
    return ' '.join(parts).lower()


def _topology(payload):
    metrics = payload.get('metrics') or {}
    topology = metrics.get('topology')
    if topology:
        return str(topology)
    sections = payload.get('sections') or {}
    if isinstance(sections, dict):
        connectivity = sections.get('connectivity') or {}
        if isinstance(connectivity, dict):
            return str(connectivity.get('topology') or '')
    return ''


def _lesson_cards(slug_reasons, limit):
    from knowledge.models import LearningLesson

    cards = []
    seen = set()
    for slug, reason in slug_reasons:
        if slug in seen:
            continue
        lesson = (
            LearningLesson.objects.select_related('track')
            .prefetch_related('tasks')
            .filter(slug=slug, is_published=True, track__is_published=True)
            .first()
        )
        if not lesson:
            continue
        task_types = []
        for task in lesson.tasks.all():
            if task.task_type not in task_types:
                task_types.append(task.task_type)
        cards.append(
            {
                'lesson_id': lesson.id,
                'lesson_slug': lesson.slug,
                'title': lesson.title,
                'track': lesson.track.title,
                'summary': lesson.summary,
                'reason': reason,
                'task_count': lesson.tasks.count(),
                'task_types': task_types,
                'url': reverse('knowledge:learning_lesson', args=[lesson.slug]),
            }
        )
        seen.add(slug)
        if len(cards) >= limit:
            break
    return cards


def learning_suggestions_from_review(review_or_report, limit=4):
    """Return learning lessons that help fix or explain review findings."""
    payload = _review_payload(review_or_report)
    text = _haystack(payload)
    topology = _topology(payload)
    slug_reasons = []

    for rule in RULES:
        if topology in rule.get('topologies', ()):
            slug_reasons.append((rule['slug'], rule['reason']))
            continue
        if any(needle in text for needle in rule.get('needles', ())):
            slug_reasons.append((rule['slug'], rule['reason']))

    if not slug_reasons:
        slug_reasons = [
            (slug, 'Базовый практикум помогает проверить расчет, схему и измерение перед повторным review.')
            for slug in FALLBACK_SLUGS
        ]

    return _lesson_cards(slug_reasons, limit)
