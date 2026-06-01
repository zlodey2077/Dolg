import json

from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .models import (
    Article,
    ArticleMaterial,
    KnowledgeCategory,
    LearningAttempt,
    LearningLesson,
    LearningProgress,
    LearningTask,
    LearningTrack,
)
from .services.engineering_lab import LAB_TOOLS, calculate_lab
from .services.learning_grader import grade_task
from .services.legal_sources import sources_by_ids, sources_for_learning_topic

PUBLIC_MATERIALS = ArticleMaterial.objects.filter(is_public=True)

CALCULATOR_LIBRARY = {
    'ohm': {
        'kind': 'ohm',
        'title': 'Закон Ома',
        'description': 'Введите любые две величины, чтобы получить третью и оценить мощность.',
    },
    'divider': {
        'kind': 'divider',
        'title': 'Делитель напряжения',
        'description': 'Быстрая проверка выходного напряжения на двух резисторах.',
    },
    'rc': {
        'kind': 'rc',
        'title': 'RC-цепь',
        'description': 'Постоянная времени и частота среза для фильтра или задержки.',
    },
    'led': {
        'kind': 'led',
        'title': 'LED-резистор',
        'description': 'Подбор токоограничивающего резистора и расчет его мощности.',
    },
    'power': {
        'kind': 'power',
        'title': 'Мощность элемента',
        'description': 'Оценка тепловой нагрузки по напряжению, току или сопротивлению.',
    },
}

CALCULATOR_RULES = [
    ('ohm', ('закон ома', 'резистор', 'ток', 'напряжение')),
    ('divider', ('делитель', 'обратная связь', 'ацп', 'резистор')),
    ('rc', ('rc-', 'rc-цеп', 'конденсатор', 'фильтр', 'сглаживание', 'задержка')),
    ('led', ('светодиод', 'led', 'диод')),
    ('power', ('мощность', 'теплов', 'нагрев', 'резистор')),
]

PRODUCT_RULES = [
    ('resistors', ('резистор', 'ом', 'делитель', 'ток', 'мощность')),
    ('capacitors', ('конденсатор', 'rc', 'фильтр', 'сглаживание', 'питания')),
    ('diodes', ('диод', 'выпрям', 'led', 'светодиод', 'стабилитрон')),
    ('transistors', ('транзистор', 'mosfet', 'bjt', 'ключ')),
    ('ics', ('микросхем', 'операционный', 'усилитель', 'стабилизатор', 'ne555', 'таймер')),
    ('inductors', ('дроссел', 'катушка', 'индуктив', 'lc')),
    ('connectors', ('разъем', 'разъём', 'соединител', 'монтаж')),
    ('relays', ('реле', 'коммутац', 'контакт')),
]


def _article_search_text(article):
    return ' '.join((
        article.title,
        article.slug,
        article.summary,
        article.body,
        article.related_components_note,
        article.category.name,
        article.category.slug,
        article.category.topic,
    )).lower()


def _article_calculators(article):
    text = _article_search_text(article)
    selected = []
    for kind, keywords in CALCULATOR_RULES:
        if any(keyword in text for keyword in keywords):
            selected.append(CALCULATOR_LIBRARY[kind])

    if article.category.topic == 'physics' and CALCULATOR_LIBRARY['ohm'] not in selected:
        selected.insert(0, CALCULATOR_LIBRARY['ohm'])

    return selected[:4]


def _related_product_slugs(article):
    text = _article_search_text(article)
    slugs = []
    for slug, keywords in PRODUCT_RULES:
        if any(keyword in text for keyword in keywords):
            slugs.append(slug)

    if article.category.topic == 'components':
        for slug in ('resistors', 'capacitors', 'diodes', 'transistors', 'ics'):
            if slug not in slugs:
                slugs.append(slug)

    return slugs[:4]


def _related_products(article):
    from shop.models import Product

    slugs = _related_product_slugs(article)
    if not slugs:
        return Product.objects.none()

    return (
        Product.objects
        .select_related('category')
        .filter(category__slug__in=slugs, stock__gt=0)
        .order_by('category__slug', 'price', 'name')[:6]
    )


def index(request):
    categories = (
        KnowledgeCategory.objects
        .prefetch_related(Prefetch(
            'articles',
            queryset=Article.objects.filter(is_published=True).only(
                'id', 'title', 'slug', 'summary', 'reading_minutes', 'category_id'
            ).prefetch_related(Prefetch('materials', queryset=PUBLIC_MATERIALS, to_attr='published_materials')),
        ))
        .all()
    )
    total = Article.objects.filter(is_published=True).count()
    return render(request, 'knowledge/index.html', {
        'categories': categories,
        'total_articles': total,
    })


def category_detail(request, slug):
    category = get_object_or_404(KnowledgeCategory, slug=slug)
    articles = category.articles.filter(is_published=True).prefetch_related(
        Prefetch('materials', queryset=PUBLIC_MATERIALS, to_attr='published_materials')
    )
    return render(request, 'knowledge/category.html', {
        'category': category,
        'articles': articles,
    })


def article_detail(request, slug):
    article = get_object_or_404(
        Article.objects.select_related('category').prefetch_related(
            Prefetch('materials', queryset=PUBLIC_MATERIALS, to_attr='published_materials')
        ),
        slug=slug,
        is_published=True,
    )
    related = (
        Article.objects
        .filter(category=article.category, is_published=True)
        .exclude(pk=article.pk)[:4]
    )
    return render(request, 'knowledge/article.html', {
        'article': article,
        'related': related,
        'calculator_tools': _article_calculators(article),
        'related_products': _related_products(article),
    })


def engineering_lab(request):
    return render(request, 'knowledge/engineering_lab.html', {
        'lab_tools': LAB_TOOLS,
    })


@require_POST
def engineering_lab_api(request):
    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
    if not payload:
        payload = request.POST.dict()

    result = calculate_lab(payload.get('kind'), payload.get('inputs') or payload)
    status = 200 if result.get('ok') else 400
    return JsonResponse(result, status=status)


def learning_index(request):
    lessons_qs = (
        LearningLesson.objects
        .filter(is_published=True)
        .prefetch_related('tasks')
        .order_by('order', 'title')
    )
    tracks = list(
        LearningTrack.objects
        .filter(is_published=True)
        .prefetch_related(Prefetch('lessons', queryset=lessons_qs, to_attr='published_lessons'))
        .order_by('order', 'title')
    )

    progress_by_lesson = {}
    if request.user.is_authenticated:
        lesson_ids = [
            lesson.id
            for track in tracks
            for lesson in getattr(track, 'published_lessons', [])
        ]
        progress_by_lesson = {
            item.lesson_id: item
            for item in LearningProgress.objects.filter(user=request.user, lesson_id__in=lesson_ids)
        }

    total_lessons = 0
    completed_lessons = 0
    for track in tracks:
        track_total = 0
        track_completed = 0
        for lesson in getattr(track, 'published_lessons', []):
            tasks = list(lesson.tasks.all())
            required_count = sum(1 for task in tasks if task.is_required)
            progress = progress_by_lesson.get(lesson.id)
            solved_ids = set(progress.solved_task_ids if progress else [])
            lesson.required_tasks_count = required_count
            lesson.solved_tasks_count = len(solved_ids)
            lesson.is_completed_for_user = bool(progress and progress.is_completed)
            track_total += 1
            track_completed += 1 if lesson.is_completed_for_user else 0
        track.lessons_count = track_total
        track.completed_lessons_count = track_completed
        total_lessons += track_total
        completed_lessons += track_completed

    return render(request, 'knowledge/learning_index.html', {
        'tracks': tracks,
        'total_lessons': total_lessons,
        'completed_lessons': completed_lessons,
    })


def learning_lesson_detail(request, slug):
    lesson = get_object_or_404(
        LearningLesson.objects
        .select_related('track', 'article', 'demo_project')
        .prefetch_related('tasks'),
        slug=slug,
        is_published=True,
        track__is_published=True,
    )
    tasks = list(lesson.tasks.all())
    lesson_sources = []
    seen_source_ids = set()
    progress = None
    solved_ids = set()
    if request.user.is_authenticated:
        progress = LearningProgress.objects.filter(user=request.user, lesson=lesson).first()
        solved_ids = set(progress.solved_task_ids if progress else [])
    for task in tasks:
        task.is_solved_for_user = task.id in solved_ids
        rubric = task.rubric if isinstance(task.rubric, dict) else {}
        task_source_ids = rubric.get('source_ids') or []
        if isinstance(task_source_ids, str):
            task_source_ids = [task_source_ids]
        task_source_topic = rubric.get('source_topic') or ''
        task.source_materials = (
            sources_by_ids(task_source_ids, limit=3)
            if task_source_ids
            else sources_for_learning_topic(task_source_topic, limit=3)
            if task_source_topic
            else []
        )
        for source in task.source_materials:
            source_id = source.get('id')
            if source_id and source_id not in seen_source_ids:
                seen_source_ids.add(source_id)
                lesson_sources.append(source)

    for topic_hint in (lesson.slug, lesson.title, lesson.summary):
        if len(lesson_sources) >= 8:
            break
        for source in sources_for_learning_topic(topic_hint, limit=5):
            source_id = source.get('id')
            if source_id and source_id not in seen_source_ids:
                seen_source_ids.add(source_id)
                lesson_sources.append(source)
            if len(lesson_sources) >= 8:
                break

    return render(request, 'knowledge/learning_lesson.html', {
        'lesson': lesson,
        'tasks': tasks,
        'progress': progress,
        'lesson_sources': lesson_sources,
    })


@require_POST
def learning_task_check(request, slug, task_id):
    lesson = get_object_or_404(
        LearningLesson,
        slug=slug,
        is_published=True,
        track__is_published=True,
    )
    task = get_object_or_404(LearningTask, pk=task_id, lesson=lesson)

    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
    if not payload:
        payload = request.POST.dict()

    result = grade_task(task, payload)
    score = max(0, min(100, int(result.get('score') or 0)))

    saved = False
    progress_payload = None
    if request.user.is_authenticated:
        saved = True
        LearningAttempt.objects.create(
            user=request.user,
            task=task,
            answer=payload if isinstance(payload, dict) else {'answer': payload},
            is_correct=bool(result.get('correct')),
            score=score,
            feedback=result.get('feedback', ''),
        )
        if result.get('correct'):
            progress, _ = LearningProgress.objects.get_or_create(
                user=request.user,
                lesson=lesson,
            )
            progress.mark_task_solved(task.id)
            progress_payload = {
                'completed': progress.is_completed,
                'solved_task_ids': progress.solved_task_ids,
            }

    return JsonResponse({
        'ok': True,
        'saved': saved,
        'correct': bool(result.get('correct')),
        'score': score,
        'feedback': result.get('feedback', ''),
        'details': result.get('details', {}),
        'progress': progress_payload,
    })
