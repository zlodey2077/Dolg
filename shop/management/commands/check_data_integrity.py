import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, override_settings

from Dolg_APP.models import SchematicProject
from knowledge.models import Article, ArticleMaterial, LearningTask
from shop import card_helpers
from shop.models import Category, Product
from shop.services.catalog_filters import CATALOG_FILTERS
from shop.services.media_quality import audit_catalog_media_quality
from shop.services.product_images import (
    GENERATED_IMAGE_SOURCE,
    is_allowed_product_image,
    is_forbidden_image_path,
)

BAD_COMMONS_TITLE_WORDS = (
    'zombie',
    'food',
    'soup',
    'noodle',
    'server room',
    'cable closet',
    'wire screens',
    'portrait',
    'meeting',
    'magazine',
)

FORBIDDEN_LEGAL_SOURCE_URL_PARTS = (
    'vk.com/doc',
    'vk.com/wall',
    't.me/',
    'telegram',
    'cloud.mail.ru',
    'disk.yandex',
    'yadi.sk',
    'mega.nz',
    'anonfiles',
    '.zip',
    '.rar',
    '.7z',
    '.djvu',
)

REQUIRED_REB_KEYS = {
    'resistors': {'resistance', 'mounting'},
    'capacitors': {'capacitance', 'mounting'},
    'transistors': {'mounting'},
    'ics': {'mounting'},
    'diodes': {'mounting'},
    'inductors': {'inductance', 'mounting'},
    'connectors': {'mounting'},
    'relays': {'mounting'},
}


class Command(BaseCommand):
    help = 'Аудитирует соответствие данных DOLG: каталог, энциклопедию, материалы и demo-схемы.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', help='Вывести полный отчет в JSON.')
        parser.add_argument('--strict', action='store_true', help='Считать предупреждения ошибками.')

    def handle(self, *args, **options):
        report = {
            'ok': True,
            'counts': {},
            'errors': [],
            'warnings': [],
            'catalog': {},
            'knowledge': {},
            'schematics': {},
            'legal_sources': {},
        }

        self._check_catalog(report)
        self._check_knowledge(report)
        self._check_schematics(report)
        self._check_legal_sources(report)

        if options['strict'] and report['warnings']:
            report['errors'].extend(f'warning-as-error: {item}' for item in report['warnings'])
        report['ok'] = not report['errors']

        if options['json']:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            self._print_human(report)

        if report['errors']:
            raise CommandError('Аудит данных нашел критичные несоответствия.')

    def _check_catalog(self, report):
        products_qs = Product.objects.select_related('category').order_by('category__slug', 'slug')
        report['counts']['products'] = products_qs.count()
        report['counts']['reb_products'] = products_qs.filter(category__slug__in=Category.REB_SLUGS).count()
        report['counts']['categories'] = Category.objects.count()
        products = list(products_qs)

        missing_images = []
        broken_images = []
        svg_images = []
        suspicious_commons = []
        forbidden_images = []
        non_policy_images = []
        duplicate_field_images = {}
        duplicate_file_hashes = {}
        invalid_reb = []
        missing_datasheets = []
        missing_datasheet_extracted = []
        suspicious_parameters = []
        invalid_lifecycle = []
        invalid_values = []
        missing_rating_limits = []
        products_with_rating_limits = 0

        seen_names = {}
        seen_hashes = {}
        media_root = Path(settings.MEDIA_ROOT)

        for product in products:
            if product.price < 0 or product.stock < 0:
                invalid_values.append(product.slug)
            if product.lifecycle_status not in dict(Product.LIFECYCLE_CHOICES):
                invalid_lifecycle.append(f'{product.slug}: {product.lifecycle_status}')

            image_name = product.image.name if product.image else ''
            if not image_name:
                missing_images.append(product.slug)
            else:
                seen_names.setdefault(image_name, []).append(product.slug)
                if is_forbidden_image_path(image_name):
                    forbidden_images.append(f'{product.slug}: {image_name}')
                if not is_allowed_product_image(product, image_name):
                    non_policy_images.append(f'{product.slug}: {image_name}')
                image_path = media_root / image_name
                if not image_path.exists():
                    broken_images.append(f'{product.slug}: {image_name}')
                else:
                    suffix = image_path.suffix.lower()
                    if suffix == '.svg' and not is_allowed_product_image(product, image_name):
                        svg_images.append(f'{product.slug}: {image_name}')
                    if suffix != '.svg':
                        file_hash = self._file_hash(image_path)
                        if file_hash:
                            seen_hashes.setdefault(file_hash, []).append(f'{product.slug}: {image_name}')

            commons_meta = media_root / 'products' / 'commons' / f'{product.slug}.txt'
            image_is_active_commons = image_name.startswith('products/commons/')
            if image_is_active_commons and commons_meta.exists():
                meta_text = commons_meta.read_text(encoding='utf-8', errors='ignore').lower()
                if any(word in meta_text for word in BAD_COMMONS_TITLE_WORDS):
                    suspicious_commons.append(product.slug)

            image_source = str((product.parameters or {}).get('image_source_url', '')).lower()
            if (
                image_source
                and image_source != GENERATED_IMAGE_SOURCE
                and is_forbidden_image_path(image_source)
            ):
                forbidden_images.append(f'{product.slug}: {image_source}')

            if product.is_reb():
                params = product.parameters or {}
                required = REQUIRED_REB_KEYS.get(product.category.slug, set())
                missing = sorted(
                    key for key in required if key not in params and not getattr(product, key, None)
                )
                if not product.part_number or not product.package_type or missing:
                    invalid_reb.append(
                        {
                            'slug': product.slug,
                            'category': product.category.slug,
                            'missing': [
                                *([] if product.part_number else ['part_number']),
                                *([] if product.package_type else ['package_type']),
                                *missing,
                            ],
                        }
                    )
                if not product.datasheet_url:
                    missing_datasheets.append(product.slug)
                if product.datasheet_url and not params.get('datasheet_extracted'):
                    missing_datasheet_extracted.append(product.slug)
                if self._has_rating_limit(params):
                    products_with_rating_limits += 1
                else:
                    missing_rating_limits.append(product.slug)
                for key, value in params.items():
                    if key == 'datasheet_extracted' or value in (None, ''):
                        continue
                    if self._looks_like_unitless_engineering_value(key, value):
                        suspicious_parameters.append(f'{product.slug}.{key}={value}')

        duplicate_field_images = {image: slugs for image, slugs in seen_names.items() if len(slugs) > 1}
        duplicate_file_hashes = {digest: refs for digest, refs in seen_hashes.items() if len(refs) > 1}
        chip_filter_coverage = self._check_chip_filter_coverage()

        catalog = report['catalog']
        catalog['missing_images'] = missing_images
        catalog['broken_images'] = broken_images
        catalog['svg_images'] = svg_images
        catalog['suspicious_commons'] = suspicious_commons
        catalog['forbidden_images'] = forbidden_images
        catalog['non_policy_images'] = non_policy_images
        catalog['duplicate_field_images'] = duplicate_field_images
        catalog['duplicate_file_hashes'] = duplicate_file_hashes
        catalog['invalid_reb'] = invalid_reb
        catalog['missing_datasheets'] = missing_datasheets
        catalog['missing_datasheet_extracted'] = missing_datasheet_extracted
        catalog['missing_rating_limits'] = missing_rating_limits
        catalog['rating_limit_coverage'] = {
            'with_limits': products_with_rating_limits,
            'without_limits': len(missing_rating_limits),
        }
        catalog['suspicious_parameters'] = suspicious_parameters[:50]
        catalog['invalid_lifecycle'] = invalid_lifecycle
        catalog['chip_filter_coverage'] = chip_filter_coverage
        catalog['invalid_values'] = invalid_values
        media_quality = audit_catalog_media_quality(products, media_root=media_root)
        catalog['media_quality'] = media_quality

        if broken_images:
            report['errors'].append(f'битые изображения товаров: {len(broken_images)}')
        if forbidden_images:
            report['errors'].append(
                f'запрещенные Wikimedia/Commons изображения товаров: {len(forbidden_images)}'
            )
        if media_quality['error_count']:
            report['errors'].append(f'media quality gate errors: {media_quality["error_count"]}')
        if media_quality['warning_count']:
            report['warnings'].append(f'media quality gate warnings: {media_quality["warning_count"]}')
        if media_quality['perceptual_duplicate_groups']:
            report['warnings'].append(
                f'perceptual duplicate product images: {len(media_quality["perceptual_duplicate_groups"])}'
            )
        if missing_images:
            report['warnings'].append(f'товары без изображения: {len(missing_images)}')
        if svg_images:
            report['warnings'].append(f'товары с SVG вместо фото: {len(svg_images)}')
        if duplicate_field_images:
            report['warnings'].append(
                f'один и тот же image привязан к нескольким товарам: {len(duplicate_field_images)}'
            )
        if duplicate_file_hashes:
            report['warnings'].append(
                f'визуальные дубли файлов товаров по hash: {len(duplicate_file_hashes)}'
            )
        if suspicious_commons:
            report['warnings'].append(f'подозрительные Commons-метаданные товаров: {len(suspicious_commons)}')
        if non_policy_images:
            report['warnings'].append(
                f'товары вне media-policy локальный asset/generated: {len(non_policy_images)}'
            )
        if invalid_reb:
            report['warnings'].append(f'РЭБ-товары с неполными инженерными полями: {len(invalid_reb)}')
        if missing_datasheets:
            report['warnings'].append(f'РЭБ-товары без datasheet_url: {len(missing_datasheets)}')
        if missing_datasheet_extracted:
            report['warnings'].append(
                f'REB products without datasheet_extracted: {len(missing_datasheet_extracted)}'
            )
        if suspicious_parameters:
            report['warnings'].append(
                f'suspicious unitless engineering parameters: {len(suspicious_parameters)}'
            )
        if invalid_lifecycle:
            report['errors'].append(f'invalid lifecycle_status values: {len(invalid_lifecycle)}')
        if chip_filter_coverage['missing_backend_filters']:
            report['errors'].append(
                f'clickable chip filters without backend support: {chip_filter_coverage["missing_backend_filters"]}'
            )
        if invalid_values:
            report['errors'].append(f'товары с отрицательной ценой/остатком: {len(invalid_values)}')

    def _check_chip_filter_coverage(self):
        backend = set(CATALOG_FILTERS)
        mapped_filters = set(card_helpers.CARD_PARAM_FILTER_MAP.values())
        return {
            'mapped_filters': sorted(mapped_filters),
            'backend_filters': sorted(backend),
            'missing_backend_filters': sorted(mapped_filters - backend),
        }

    @staticmethod
    def _has_rating_limit(params):
        params = params or {}
        direct_keys = {
            'max_voltage_v',
            'max_voltage',
            'voltage',
            'supply_voltage',
            'max_current_a',
            'max_current',
            'current',
            'output_current',
            'max_power_w',
            'rated_power_w',
            'tdp_w',
            'power',
            'max_power',
            'max_junction_c',
            'max_temperature_c',
            'max_temp',
            'temperature',
        }
        if any(key in params and params.get(key) not in (None, '') for key in direct_keys):
            return True
        record = params.get('datasheet_extracted')
        fields = record.get('fields') if isinstance(record, dict) else {}
        if not isinstance(fields, dict):
            return False
        return any(
            fields.get(key)
            for key in (
                'absolute_maximum_ratings',
                'recommended_operating_conditions',
                'thermal_data',
            )
        )

    @staticmethod
    def _looks_like_unitless_engineering_value(key, value):
        key = str(key).lower()
        unit_sensitive = {
            'resistance',
            'capacitance',
            'inductance',
            'voltage',
            'supply_voltage',
            'power',
            'wattage',
            'current',
        }
        if key not in unit_sensitive:
            return False
        return bool(re.fullmatch(r'[-+]?\d+(?:[.,]\d+)?', str(value).strip()))

    def _check_knowledge(self, report):
        articles = (
            Article.objects.select_related('category')
            .prefetch_related('materials')
            .order_by('category__slug', 'slug')
        )
        materials = ArticleMaterial.objects.select_related('article').filter(is_public=True)
        report['counts']['published_articles'] = articles.filter(is_published=True).count()
        report['counts']['article_materials'] = materials.count()

        no_materials = []
        no_inline_media = []
        broken_local_files = []
        internal_links = set()

        for article in articles:
            article_materials = list(article.materials.filter(is_public=True))
            if not article_materials:
                no_materials.append(article.slug)
            if not any(m.renders_inline for m in article_materials):
                no_inline_media.append(article.slug)
            for href in self._extract_internal_links(article.body):
                internal_links.add(href)

        for material in materials:
            href = material.href
            if not href:
                continue
            if href.startswith('/media/'):
                rel = href.replace(settings.MEDIA_URL, '', 1).lstrip('/')
                if not (Path(settings.MEDIA_ROOT) / rel).exists():
                    broken_local_files.append(f'{material.article.slug}: {href}')
            elif href.startswith('/'):
                internal_links.add(href)
            if material.file and not Path(material.file.path).exists():
                broken_local_files.append(f'{material.article.slug}: {material.file.name}')

        broken_internal_links = self._check_internal_links(sorted(internal_links))

        knowledge = report['knowledge']
        knowledge['articles_without_materials'] = no_materials
        knowledge['articles_without_inline_media'] = no_inline_media
        knowledge['broken_local_files'] = broken_local_files
        knowledge['broken_internal_links'] = broken_internal_links

        if broken_local_files:
            report['errors'].append(f'битые файлы материалов энциклопедии: {len(broken_local_files)}')
        if broken_internal_links:
            report['warnings'].append(
                f'подозрительные/битые внутренние ссылки энциклопедии: {len(broken_internal_links)}'
            )
        if no_materials:
            report['warnings'].append(f'статьи без дополнительных материалов: {len(no_materials)}')
        if no_inline_media:
            report['warnings'].append(f'статьи без inline фото/видео/gif: {len(no_inline_media)}')

    def _check_schematics(self, report):
        projects = SchematicProject.objects.filter(is_demo=True).order_by('name')
        report['counts']['demo_projects'] = projects.count()

        invalid_projects = []
        warnings = []
        for project in projects:
            result = self._validate_scheme(project.scheme_data or {})
            if result['errors']:
                invalid_projects.append({'name': project.name, 'errors': result['errors']})
            if result['warnings']:
                warnings.append({'name': project.name, 'warnings': result['warnings']})

        report['schematics']['invalid_projects'] = invalid_projects
        report['schematics']['warnings'] = warnings
        if invalid_projects:
            report['errors'].append(f'demo-схемы с критичными ошибками: {len(invalid_projects)}')
        if warnings:
            report['warnings'].append(f'demo-схемы с замечаниями компоновки/данных: {len(warnings)}')

    def _validate_scheme(self, scheme):
        result = {'errors': [], 'warnings': []}
        components = scheme.get('components') or []
        connections = scheme.get('connections') or []
        if not components:
            result['errors'].append('нет компонентов')
            return result
        if not connections:
            result['warnings'].append('нет соединений')

        ids = [c.get('id') for c in components]
        if len(ids) != len(set(ids)):
            result['errors'].append('дублирующиеся id компонентов')
        by_id = {c.get('id'): c for c in components}
        has_ground = any(str(c.get('type', '')).lower() == 'ground' for c in components)
        if not has_ground:
            result['warnings'].append('нет символа GND')

        for comp in components:
            if 'x' not in comp or 'y' not in comp:
                result['errors'].append(f'компонент {comp.get("id")} без координат')
            if not comp.get('ports'):
                result['warnings'].append(f'компонент {comp.get("id")} без ports')

        for index, conn in enumerate(connections):
            for side in ('from', 'to'):
                endpoint = conn.get(side) or {}
                comp_id = endpoint.get('compId')
                port_id = endpoint.get('portId')
                comp = by_id.get(comp_id)
                if not comp:
                    result['errors'].append(
                        f'соединение {index}: {side} указывает на отсутствующий компонент {comp_id}'
                    )
                    continue
                ports = {p.get('id') for p in comp.get('ports', [])}
                if port_id not in ports:
                    result['errors'].append(
                        f'соединение {index}: порт {port_id} отсутствует у компонента {comp_id}'
                    )
            for point in conn.get('waypoints') or []:
                if 'x' not in point or 'y' not in point:
                    result['errors'].append(f'соединение {index}: waypoint без координат')

        xs = [self._as_float(c.get('x')) for c in components]
        ys = [self._as_float(c.get('y')) for c in components]
        if max(xs) - min(xs) > 1800 or max(ys) - min(ys) > 1100:
            result['warnings'].append('схема слишком крупная для удобного первого просмотра')
        return result

    def _check_legal_sources(self, report):
        legal = report['legal_sources']
        try:
            from Dolg_APP.models import AITrainingExample
            from Dolg_APP.services.expert_rules import load_rule_pack
            from knowledge.services.legal_sources import load_legal_sources, validate_source_ids
        except Exception as exc:
            legal['error'] = str(exc)
            report['errors'].append(f'legal sources integrity import failed: {exc}')
            return

        try:
            sources = load_legal_sources()
        except Exception as exc:
            legal['error'] = str(exc)
            report['errors'].append(f'legal sources integrity failed: {exc}')
            return

        invalid_urls = []
        forbidden_urls = []
        duplicate_ids = []
        seen_ids = set()
        for source in sources:
            source_id = source.get('id')
            url = source.get('url') or ''
            if source_id in seen_ids:
                duplicate_ids.append(source_id)
            seen_ids.add(source_id)
            if not url.startswith('https://'):
                invalid_urls.append(f'{source_id}: {url}')
            if any(part in url.lower() for part in FORBIDDEN_LEGAL_SOURCE_URL_PARTS):
                forbidden_urls.append(f'{source_id}: {url}')

        rule_source_errors = []
        for rule in load_rule_pack().get('rules') or []:
            references = rule.get('references') if isinstance(rule.get('references'), dict) else {}
            missing = validate_source_ids(references.get('source_ids') or [])
            if missing:
                rule_source_errors.append(
                    {
                        'rule_id': rule.get('id'),
                        'missing_source_ids': missing,
                    }
                )

        task_source_errors = []
        tasks_with_sources = 0
        for task in LearningTask.objects.select_related('lesson').all():
            rubric = task.rubric if isinstance(task.rubric, dict) else {}
            source_ids = rubric.get('source_ids') or []
            if isinstance(source_ids, str):
                source_ids = [source_ids]
            if source_ids:
                tasks_with_sources += 1
            missing = validate_source_ids(source_ids)
            if missing:
                task_source_errors.append(
                    {
                        'task_id': task.id,
                        'title': task.title,
                        'missing_source_ids': missing,
                    }
                )

        training_source_errors = []
        training_examples_with_sources = 0
        for example in AITrainingExample.objects.all()[:1000]:
            features = example.features if isinstance(example.features, dict) else {}
            source_ids = features.get('source_ids') or []
            if isinstance(source_ids, str):
                source_ids = [source_ids]
            if source_ids or features.get('source_topics') or features.get('teacher_rules'):
                training_examples_with_sources += 1
            missing = validate_source_ids(source_ids)
            if missing:
                training_source_errors.append(
                    {
                        'example_id': example.id,
                        'kind': example.kind,
                        'missing_source_ids': missing,
                    }
                )

        legal.update(
            {
                'count': len(sources),
                'invalid_urls': invalid_urls,
                'forbidden_urls': forbidden_urls,
                'duplicate_ids': duplicate_ids,
                'rule_source_errors': rule_source_errors,
                'task_source_errors': task_source_errors,
                'training_source_errors': training_source_errors,
                'tasks_with_sources': tasks_with_sources,
                'training_examples_with_sources': training_examples_with_sources,
            }
        )

        if invalid_urls:
            report['errors'].append(f'legal source urls must be https: {len(invalid_urls)}')
        if forbidden_urls:
            report['errors'].append(
                f'legal source urls include forbidden archive/download sources: {len(forbidden_urls)}'
            )
        if duplicate_ids:
            report['errors'].append(f'duplicate legal source ids: {len(duplicate_ids)}')
        if rule_source_errors:
            report['errors'].append(
                f'expert rules reference unknown legal sources: {len(rule_source_errors)}'
            )
        if task_source_errors:
            report['errors'].append(
                f'learning tasks reference unknown legal sources: {len(task_source_errors)}'
            )
        if training_source_errors:
            report['errors'].append(
                f'AI training examples reference unknown legal sources: {len(training_source_errors)}'
            )

    def _check_internal_links(self, hrefs):
        if not hrefs:
            return []
        static_storage = {
            'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
        }
        broken = []
        with override_settings(
            ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
            STORAGES=static_storage,
            SECURE_SSL_REDIRECT=False,
            SESSION_COOKIE_SECURE=False,
            CSRF_COOKIE_SECURE=False,
        ):
            client = Client()
            for href in hrefs:
                if href.startswith(settings.MEDIA_URL) or href.startswith(settings.STATIC_URL):
                    continue
                try:
                    response = client.get(href, follow=False)
                    if response.status_code >= 400 and response.status_code not in {401, 403, 405}:
                        broken.append({'url': href, 'status': response.status_code})
                except Exception as exc:
                    broken.append({'url': href, 'error': str(exc)})
        return broken

    @staticmethod
    def _extract_internal_links(html):
        if not html:
            return []
        return [
            match
            for match in re.findall(r"""(?:href|src)=["']([^"']+)["']""", html, flags=re.IGNORECASE)
            if match.startswith('/')
        ]

    @staticmethod
    def _file_hash(path):
        try:
            digest = hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            return ''

    @staticmethod
    def _as_float(value):
        try:
            return float(value)
        except TypeError, ValueError:
            return 0.0

    def _print_human(self, report):
        self.stdout.write(self.style.SUCCESS('DOLG data integrity report'))
        for key, value in report['counts'].items():
            self.stdout.write(f'  {key}: {value}')
        for key in ('errors', 'warnings'):
            items = report[key]
            if not items:
                continue
            style = self.style.ERROR if key == 'errors' else self.style.WARNING
            self.stdout.write(style(f'{key}:'))
            for item in items:
                self.stdout.write(f'  - {item}')
        if report['ok']:
            self.stdout.write(self.style.SUCCESS('OK: критичных несоответствий не найдено.'))
