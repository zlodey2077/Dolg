import json

from django.core.management.base import BaseCommand
from django.db import transaction

from knowledge.models import Article, ArticleMaterial, KnowledgeCategory, LearningLesson, LearningTask, LearningTrack
from knowledge.services.legal_sources import load_legal_sources, summarize_legal_sources


OVERVIEW_TITLE = 'Открытые источники и документация DOLG'
OVERVIEW_SLUG = 'otkrytye-istochniki-i-dokumentatsiya-dolg'

SOURCE_LEARNING_TRACK = {
    'title': 'Практика по открытым инженерным источникам',
    'slug': 'praktika-po-otkrytym-inzhenernym-istochnikam',
    'summary': 'Задания DOLG, основанные на открытых учебниках, официальной документации и собственных проверках проекта.',
    'level': 'medium',
    'order': 70,
    'lessons': [
        {
            'title': 'Формулы цепей: Ом, делитель и RC',
            'slug': 'source-backed-ohm-divider-rc',
            'summary': 'Расчетные задачи с проверяемыми источниками и теми же формулами, что использует лаборатория.',
            'theory': '<p>В этом уроке используются закон Ома, делитель напряжения и частота среза RC-цепи. Источники нужны как проверяемая опора, а сами задания сформулированы в DOLG.</p>',
            'formula': 'U = I · R; Vout = Vin · R2 / (R1 + R2); fc = 1 / (2πRC)',
            'article_query': 'Закон Ома',
            'action_url': '/knowledge/lab/',
            'action_label': 'Открыть лабораторию',
            'order': 10,
            'tasks': [
                {
                    'title': 'Закон Ома: ток через резистор',
                    'task_type': 'math_numeric',
                    'prompt': 'Резистор 1 кОм подключен к 5 В. Найдите ток в мА.',
                    'rubric': {
                        'expected_value': 5,
                        'unit': 'мА',
                        'tolerance_abs': 0.05,
                        'source_ids': ['all_about_circuits_textbook', 'openstax_university_physics_2', 'sympy_docs'],
                        'source_topic': 'ohm',
                        'teacher_rule': 'formula.ohm_law',
                    },
                    'order': 10,
                },
                {
                    'title': 'Делитель 9 В -> около 3 В',
                    'task_type': 'math_numeric',
                    'prompt': 'Для делителя Vin=9 В, R1=6.8 кОм, R2=3.3 кОм найдите Vout.',
                    'rubric': {
                        'expected_value': 2.94,
                        'unit': 'В',
                        'tolerance_abs': 0.08,
                        'source_ids': ['all_about_circuits_textbook', 'openstax_university_physics_2', 'z3_guide'],
                        'source_topic': 'divider',
                        'teacher_rule': 'topology.divider_without_output',
                    },
                    'order': 20,
                },
                {
                    'title': 'RC cutoff',
                    'task_type': 'math_numeric',
                    'prompt': 'Найдите частоту среза RC-фильтра: R=10 кОм, C=100 нФ.',
                    'rubric': {
                        'expected_value': 159.15,
                        'unit': 'Гц',
                        'tolerance_percent': 2,
                        'source_ids': ['all_about_circuits_textbook', 'openstax_university_physics_2', 'ngspice_docs'],
                        'source_topic': 'rc',
                        'teacher_rule': 'simulation.no_saved_measurements',
                    },
                    'order': 30,
                },
            ],
        },
        {
            'title': 'SPICE и GND как проверяемая схема',
            'slug': 'source-backed-spice-gnd-drc',
            'summary': 'Практика по GND, netlist/import и базовым DRC-проверкам.',
            'theory': '<p>SPICE-схеме нужен опорный узел. После импорта схема должна пройти нормализацию, DRC/ERC и review.</p>',
            'formula': 'node 0 = GND',
            'article_query': 'DRC',
            'action_url': '/cad/',
            'action_label': 'Открыть CAD',
            'order': 20,
            'tasks': [
                {
                    'title': 'GND в SPICE-схеме',
                    'task_type': 'circuit_build',
                    'prompt': 'Соберите схему из источника, резистора и GND. Схема должна быть связной.',
                    'rubric': {
                        'required_types': {'battery': 1, 'resistor': 1, 'ground': 1},
                        'require_ground': True,
                        'require_source': True,
                        'require_connected': True,
                        'min_connections': 2,
                        'source_ids': ['ngspice_docs', 'kicad_docs', 'all_about_circuits_textbook'],
                        'source_topic': 'gnd',
                        'teacher_rule': 'erc.missing_ground',
                    },
                    'order': 10,
                },
                {
                    'title': 'Делитель после SPICE-import',
                    'task_type': 'circuit_build',
                    'prompt': 'Вставьте scheme_data делителя: источник, два резистора, GND и не менее трех соединений.',
                    'rubric': {
                        'required_types': {'battery': 1, 'resistor': 2, 'ground': 1},
                        'require_ground': True,
                        'require_source': True,
                        'require_connected': True,
                        'min_connections': 3,
                        'source_ids': ['ngspice_docs', 'lark_docs', 'kicad_docs'],
                        'source_topic': 'spice',
                        'teacher_rule': 'import.unsupported_items',
                    },
                    'order': 20,
                },
                {
                    'title': 'DRC: floating fragment',
                    'task_type': 'circuit_build',
                    'prompt': 'Соберите связанную схему без плавающих фрагментов: источник, два резистора, GND.',
                    'rubric': {
                        'required_types': {'battery': 1, 'resistor': 2, 'ground': 1},
                        'require_ground': True,
                        'require_source': True,
                        'require_connected': True,
                        'min_connections': 3,
                        'source_ids': ['networkx_algorithms', 'kicad_docs'],
                        'source_topic': 'drc',
                        'teacher_rule': 'topology.floating_fragments',
                    },
                    'order': 30,
                },
            ],
        },
        {
            'title': 'Единицы, измерения и подбор номиналов',
            'slug': 'source-backed-units-measurements-constraints',
            'summary': 'Unit-aware ввод, измерение результата и constraint-подбор номинала.',
            'theory': '<p>DOLG должен понимать инженерные единицы и проверять результат через расчет, схему и измерение.</p>',
            'formula': 'R = (Vin - Vf) / Iled',
            'article_query': 'Резистор',
            'action_url': '/knowledge/lab/',
            'action_label': 'Открыть лабораторию',
            'order': 30,
            'tasks': [
                {
                    'title': 'Unit parsing: 10k, 100 nF, 0.25 W',
                    'task_type': 'math_numeric',
                    'prompt': 'Введите мощность 0.25 W в ваттах.',
                    'rubric': {
                        'expected_value': 0.25,
                        'unit': 'Вт',
                        'tolerance_abs': 0.001,
                        'source_ids': ['pint_docs'],
                        'source_topic': 'units',
                        'teacher_rule': 'unit.parse_nominal',
                    },
                    'order': 10,
                },
                {
                    'title': 'Измерить Vout делителя',
                    'task_type': 'simulation_measure',
                    'prompt': 'Отправьте DC-результат делителя 9 В с Vout около 2.94 В.',
                    'rubric': {
                        'required_analysis': 'dc',
                        'metric': 'node_voltage',
                        'node': 'out',
                        'expected_value': 2.94,
                        'unit': 'В',
                        'tolerance_abs': 0.12,
                        'source_ids': ['ngspice_docs', 'ltspice_analog_devices'],
                        'source_topic': 'spice',
                        'teacher_rule': 'simulation.no_saved_measurements',
                    },
                    'order': 20,
                },
                {
                    'title': 'LED-резистор по ограничениям',
                    'task_type': 'math_numeric',
                    'prompt': 'Для Vin=5 В, Vf=2 В, Iled=10 мА найдите ближайшее расчетное сопротивление.',
                    'rubric': {
                        'expected_value': 300,
                        'unit': 'Ом',
                        'tolerance_percent': 5,
                        'source_ids': ['all_about_circuits_textbook', 'z3_guide'],
                        'source_topic': 'constraints',
                        'teacher_rule': 'erc.led_reverse_polarity',
                    },
                    'order': 30,
                },
            ],
        },
    ],
}


def _overview_body(sources):
    grouped = {}
    for item in sources:
        grouped.setdefault(item['topic'], []).append(item)

    blocks = [
        '<p>В этом разделе собраны легальные источники, на которые опираются '
        'энциклопедия, практикум, Engineering Review, лаборатория и AI-помощник DOLG.</p>',
        '<p>Внешние подборки книг используются только как ориентир по темам и названиям. '
        'В код, диплом и обучающий корпус попадают официальная документация, открытые '
        'учебники, datasheet, demo-проекты и пользовательские схемы с явным согласием.</p>',
    ]
    for topic in sorted(grouped):
        blocks.append(f'<h3>{topic}</h3>')
        blocks.append('<ul>')
        for item in sorted(grouped[topic], key=lambda row: row['order']):
            blocks.append(
                f'<li><a href="{item["url"]}">{item["title"]}</a> — '
                f'{item["description"]}</li>'
            )
        blocks.append('</ul>')
    return '\n'.join(blocks)


class Command(BaseCommand):
    help = 'Добавляет легальные открытые источники в энциклопедию как ArticleMaterial.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Показать план без записи в БД.')
        parser.add_argument('--json', action='store_true', help='Вывести результат в JSON.')
        parser.add_argument(
            '--no-overview',
            action='store_true',
            help='Не создавать обзорную статью со всеми источниками.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        sources = load_legal_sources()
        summary = summarize_legal_sources(sources)
        result = {
            'ok': True,
            'sources': summary,
            'overview_article': None,
            'materials_created': 0,
            'materials_updated': 0,
            'learning_lessons': 0,
            'learning_tasks': 0,
            'missing_article_slugs': [],
            'dry_run': bool(options['dry_run']),
        }

        if options['dry_run']:
            self._print_result(result, options['json'])
            transaction.set_rollback(True)
            return

        overview_article = None
        if not options['no_overview']:
            category, _ = KnowledgeCategory.objects.update_or_create(
                topic='practice',
                defaults={
                    'name': 'Инженерная практика',
                    'slug': 'инженерная-практика',
                    'icon': '🛠',
                    'description': 'Проектирование, проверка, сборка и инженерные источники.',
                    'order': 60,
                },
            )
            overview_article, _ = Article.objects.update_or_create(
                slug=OVERVIEW_SLUG,
                defaults={
                    'category': category,
                    'title': OVERVIEW_TITLE,
                    'summary': (
                        'Легальные открытые источники для энциклопедии, практикума, '
                        'review, AI-помощника и дипломной библиографии.'
                    ),
                    'body': _overview_body(sources),
                    'related_components_note': 'Официальная документация, открытые учебники и datasheet.',
                    'reading_minutes': 5,
                    'is_published': True,
                    'order': 900,
                },
            )
            ArticleMaterial.objects.update_or_create(
                article=overview_article,
                title='Схема легального корпуса знаний DOLG',
                defaults={
                    'material_type': 'image',
                    'description': 'Техническая схема источников: open textbooks, official docs, datasheet, demo-схемы, review, learning и AI context.',
                    'url': '/static/knowledge/legal_sources.svg',
                    'order': 1,
                    'is_public': True,
                },
            )
            result['overview_article'] = overview_article.slug

        for item in sources:
            targets = []
            if overview_article is not None:
                targets.append(overview_article)
            for slug in item['related_article_slugs']:
                article = Article.objects.filter(slug=slug).first()
                if article is None:
                    result['missing_article_slugs'].append(slug)
                    continue
                targets.append(article)

            for article in dict.fromkeys(targets):
                title = f'Источник: {item["title"]}'
                description = item['description']
                if item['license_note']:
                    description = f'{description} Правовая пометка: {item["license_note"]}'
                description = description[:300]
                _, created = ArticleMaterial.objects.update_or_create(
                    article=article,
                    title=title[:160],
                    defaults={
                        'material_type': 'external',
                        'description': description,
                        'url': item['url'],
                        'order': item['order'],
                        'is_public': True,
                    },
                )
                if created:
                    result['materials_created'] += 1
                else:
                    result['materials_updated'] += 1

        result['missing_article_slugs'] = sorted(set(result['missing_article_slugs']))
        self._seed_source_learning(result)
        result['ok'] = not result['missing_article_slugs']
        self._print_result(result, options['json'])

    def _seed_source_learning(self, result):
        track_data = SOURCE_LEARNING_TRACK
        track, _ = LearningTrack.objects.update_or_create(
            slug=track_data['slug'],
            defaults={
                'title': track_data['title'],
                'summary': track_data['summary'],
                'level': track_data['level'],
                'order': track_data['order'],
                'is_published': True,
            },
        )
        for lesson_data in track_data['lessons']:
            article = None
            if lesson_data.get('article_query'):
                article = Article.objects.filter(title__icontains=lesson_data['article_query']).first()
            lesson, _ = LearningLesson.objects.update_or_create(
                slug=lesson_data['slug'],
                defaults={
                    'track': track,
                    'title': lesson_data['title'],
                    'summary': lesson_data['summary'],
                    'theory': lesson_data['theory'],
                    'formula': lesson_data.get('formula', ''),
                    'article': article,
                    'action_url': lesson_data.get('action_url', '/knowledge/lab/'),
                    'action_label': lesson_data.get('action_label', 'Открыть инструмент'),
                    'estimated_minutes': lesson_data.get('estimated_minutes', 9),
                    'order': lesson_data.get('order', 100),
                    'is_published': True,
                },
            )
            result['learning_lessons'] += 1
            for task_data in lesson_data['tasks']:
                LearningTask.objects.update_or_create(
                    lesson=lesson,
                    title=task_data['title'],
                    defaults={
                        'task_type': task_data['task_type'],
                        'prompt': task_data['prompt'],
                        'rubric': task_data['rubric'],
                        'order': task_data.get('order', 100),
                        'is_required': task_data.get('is_required', True),
                    },
                )
                result['learning_tasks'] += 1

    def _print_result(self, result, as_json):
        if as_json:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
            return
        self.stdout.write(self.style.SUCCESS(
            f'OK: источников {result["sources"]["count"]}, '
            f'создано материалов {result["materials_created"]}, '
            f'обновлено {result["materials_updated"]}'
        ))
        if result['overview_article']:
            self.stdout.write(f'Обзорная статья: {result["overview_article"]}')
        if result['missing_article_slugs']:
            self.stdout.write(self.style.WARNING(
                'Не найдены статьи: ' + ', '.join(result['missing_article_slugs'])
            ))
