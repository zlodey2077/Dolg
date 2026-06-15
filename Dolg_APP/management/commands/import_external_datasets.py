"""Импорт открытых datasets схем для расширения training base нейронки.

Использование:
    # Скачать Open Schematics (CC-BY-4.0, главный приз: 84k KiCad-схем)
    python manage.py import_external_datasets --source open_schematics --limit 500

    # Импорт SPICE-netlist'ов из локально клонированного репо
    python manage.py import_external_datasets --source spice_dir --path ./some/repo

    # Dry-run чтобы оценить размер до реального import'а
    python manage.py import_external_datasets --source open_schematics --limit 100 --dry-run

Зависимости:
    pip install -r requirements-ai.txt  # тянет datasets + pyarrow + huggingface-hub

Output:
    Dolg_APP/ml/dataset/external/<source>_<timestamp>.json — chunk с импортом
    + (опц.) AITrainingExample rows если --persist
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

# Windows: stdout по умолчанию cp1251 — ✓/✗/emoji ломают UnicodeEncodeError.
# Принудительно переключаем на utf-8 c errors='replace', чтобы команда
# никогда не падала на logging-сообщениях (актуальный фейл от 2026-05-27).
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

DATASET_DIR = Path('Dolg_APP/ml/dataset/external')

SUPPORTED_SOURCES = {
    'open_schematics': {
        'hf_id': 'bshada/open-schematics',
        'license': 'CC-BY-4.0',
        'attribution': 'Open Schematics (bshada) — CC-BY-4.0',
        'description': '84 470 KiCad-схем, parquet + готовый JSON + PNG',
        'split': 'train',
    },
    'spice_dir': {
        'license': 'varies',
        'attribution': 'GitHub SPICE collection (см. --path)',
        'description': 'Локальная директория с .cir/.sp/.asc файлами',
    },
}


def _safe_iter_batches(pf, cmd, shard_no, columns=None):
    """Итерирует batch'и parquet устойчиво: при битой странице (повреждённый/
    недокачанный шард → TProtocolException и т.п.) не роняет весь импорт, а
    отдаёт прочитанное до ошибки и останавливается с предупреждением.

    `columns` — читать только нужные колонки. Тяжёлый бинарный `image` (PNG)
    исключается: его страницы бьются (TProtocolException) и роняли весь шард,
    хотя парсер схему берёт из текстовых полей. Без него шард читается целиком."""
    iterator = pf.iter_batches(batch_size=64, columns=columns)
    while True:
        try:
            batch = next(iterator)
        except StopIteration:
            return
        except Exception as exc:
            cmd.stdout.write(
                cmd.style.WARNING(
                    f'  ⚠ шард {shard_no}: parquet повреждён, чтение прервано '
                    f'({type(exc).__name__}: {str(exc)[:120]}) — беру прочитанное до этой точки'
                )
            )
            return
        yield batch


class Command(BaseCommand):
    help = 'Импорт открытых datasets схем (HuggingFace / GitHub SPICE) в training base.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            choices=sorted(SUPPORTED_SOURCES.keys()),
            required=True,
            help='Источник datasets для импорта.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=500,
            help='Максимум схем для импорта (default 500). Open Schematics — 84 470 итого.',
        )
        parser.add_argument('--path', type=str, default=None, help='Локальный путь (для --source spice_dir).')
        parser.add_argument(
            '--min-components', type=int, default=3, help='Минимум компонентов в схеме (фильтр шума).'
        )
        parser.add_argument(
            '--max-components', type=int, default=50, help='Максимум компонентов (фильтр гигантских схем).'
        )
        parser.add_argument(
            '--persist',
            action='store_true',
            help='Сохранить в AITrainingExample модели БД (иначе только в JSON-файл).',
        )
        parser.add_argument(
            '--dry-run', action='store_true', help='Показать что бы импортировалось без записи.'
        )
        parser.add_argument(
            '--progress-cache-key',
            type=str,
            default=None,
            help='Если указан, команда будет писать live-прогресс в Django cache по этому ключу '
            '(используется admin-страницей /staff/ml-training/ для UI-полоски прогресса).',
        )
        parser.add_argument(
            '--shards',
            type=int,
            default=1,
            help='Сколько parquet-шардов скачать из открытого датасета (1..78). '
            'Каждый шард ≈1000-1100 схем, 50-80 МБ. По умолчанию 1 (для быстрой проверки). '
            '--shards 78 = все 84к схем, ~4-6 ГБ диска и 30-60 мин на загрузку.',
        )
        parser.add_argument(
            '--start-shard',
            type=int,
            default=0,
            help='С какого шарда начинать (0..77). Полезно пропустить битый shard-0 '
            '(--start-shard 1) или возобновить прерванную загрузку.',
        )

        parser.add_argument(
            '--local-only', action='store_true', help='Use only local HuggingFace cache; do not open network.'
        )
        parser.add_argument(
            '--as-projects',
            action='store_true',
            help='Also create demo SchematicProject rows for accepted imported schemes.',
        )
        parser.add_argument(
            '--project-min-quality',
            type=int,
            default=60,
            help='Minimum expert quality score for --as-projects.',
        )
        parser.add_argument(
            '--download-deadline',
            type=int,
            default=120,
            help='Maximum seconds for one parquet shard download before skipping it.',
        )

    def handle(self, *args, **opts):
        source = opts['source']
        spec = SUPPORTED_SOURCES[source]
        self.stdout.write(self.style.SUCCESS(f'\n=== Импорт: {source} ==='))
        self.stdout.write(f'License: {spec["license"]}')
        self.stdout.write(f'Description: {spec["description"]}\n')

        DATASET_DIR.mkdir(parents=True, exist_ok=True)

        if source == 'open_schematics':
            schemes = self._import_open_schematics(opts)
        elif source == 'spice_dir':
            schemes = self._import_spice_dir(opts)
        else:
            raise CommandError(f'Unknown source: {source}')

        if not schemes:
            self.stdout.write(self.style.WARNING('Нет схем для импорта.'))
            return

        # Output: JSON-файл в Dolg_APP/ml/dataset/external/
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        out_path = DATASET_DIR / f'{source}_{timestamp}.json'
        payload = {
            'source': source,
            'license': spec['license'],
            'attribution': spec['attribution'],
            'imported_at': timestamp,
            'count': len(schemes),
            'schemes': schemes,
        }

        if opts['dry_run']:
            self.stdout.write(
                self.style.WARNING(
                    f'[dry-run] Готово к импорту: {len(schemes)} схем в {out_path} '
                    f'(~{round(len(json.dumps(payload)) / 1024)} КБ JSON).'
                )
            )
            return

        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Сохранено: {out_path} ({round(out_path.stat().st_size / 1024)} КБ, {len(schemes)} схем)'
            )
        )

        if opts['persist']:
            self._persist_to_db(schemes, source, spec)
        if opts.get('as_projects'):
            self._persist_to_projects(
                schemes,
                source,
                spec,
                min_quality=int(opts.get('project_min_quality') or 60),
            )

        self.stdout.write('\nДальше:')
        self.stdout.write(f'  python manage.py train_tiny_circuit_ai --dataset {out_path} --epochs 200')
        self.stdout.write('  или интегрировать в curated set: --include-curated после --persist')

    # ----- Sources -------------------------------------------------------

    def _import_open_schematics(self, opts):
        """Импорт HuggingFace dataset bshada/open-schematics.

        Стратегия: НЕ streaming через `datasets.load_dataset`, а прямая загрузка
        ОДНОГО parquet-шарда через `hf_hub_download` + pyarrow.iter_batches.
        Причины (выбило 3 раза):
        - streaming + httpx иногда закрывает client mid-iteration.
        - HF rate-limit (429) при анонимке.
        - PIL.Image (поле png) ломается на битых картинках в `decode_batch`.
        Direct parquet-чтение всё это обходит — pyarrow читает binary как байты.
        Один шард ≈ 1000-1100 схем, 50-80 МБ. Этого хватит на limit до ~1000.
        """
        try:
            import pyarrow.parquet as pq
        except ImportError as err:
            raise CommandError(
                'Не установлены huggingface-hub или pyarrow. Запустите:\n  pip install -r requirements-ai.txt'
            ) from err

        spec = SUPPORTED_SOURCES['open_schematics']
        limit = max(1, int(opts['limit']))
        self.stdout.write(f'Скачиваю первый parquet-шард с HuggingFace: {spec["hf_id"]} (до {limit} схем)…')

        # Прогресс
        progress_key = opts.get('progress_cache_key')
        started_at = time.time()
        cache_obj = None
        if progress_key:
            try:
                from django.core.cache import cache as cache_obj
            except Exception:
                cache_obj = None

        def _publish_progress(state='running', extra=None):
            if not cache_obj or not progress_key:
                return
            payload = {
                'state': state,
                'source': 'open_schematics',
                'limit': limit,
                'processed': processed,
                'imported': len(out),
                'skipped': skipped,
                'decode_errors': decode_errors,
                'started_at': started_at,
                'heartbeat_at': time.time(),
                'server_time': time.time(),
                'elapsed': round(time.time() - started_at, 1),
                'message': (
                    extra.get('message')
                    if extra and 'message' in extra
                    else f'Обработано {processed} строк, импортировано {len(out)}, пропущено {skipped}'
                ),
            }
            if extra:
                payload.update(extra)
            try:
                cache_obj.set(progress_key, payload, timeout=7200)
            except Exception:
                pass

        out = []
        skipped = 0
        processed = 0
        decode_errors = 0
        _publish_progress(extra={'message': 'Скачиваю parquet-шард…'})

        shards_to_pull = max(1, min(78, int(opts.get('shards') or 1)))
        start_shard = max(0, min(77, int(opts.get('start_shard') or 0)))
        # HF_TOKEN из env — даёт ×10 rate-limit и стабильную загрузку.
        # Без токена анонимы часто получают 429 или connection hang.
        import os as _os

        hf_token = _os.getenv('HF_TOKEN') or _os.getenv('HUGGINGFACE_TOKEN')
        if hf_token:
            self.stdout.write(
                f'  HF_TOKEN найден ({len(hf_token)} символов) — использую authenticated загрузку.'
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    '  HF_TOKEN не задан — анонимная загрузка может быть медленной/зависать. '
                    'Получить токен: https://huggingface.co/settings/tokens, добавить в .env как HF_TOKEN=hf_...'
                )
            )
        from Dolg_APP.services.cad_import import import_kicad_sexpr

        # Авто-детект ключа со схемой: пробуем несколько типичных имён.
        TEXT_KEYS = ('schematic', 'kicad_sch', 'sch', 'content', 'text', 'data', 'kicad', 'source')
        JSON_KEYS = ('json', 'metadata', 'components_json', 'parsed')
        first_row_dumped = False

        # Watcher-поток обновляет UI размером кеш-папки HF во время скачивания.
        # hf_hub_download не даёт callback, но файл `*.incomplete` растёт по мере
        # загрузки — следим за ним и публикуем «Скачано X МБ из ~Y».
        import threading
        from pathlib import Path as _Path

        from huggingface_hub.constants import HF_HUB_CACHE

        cache_dir = _Path(HF_HUB_CACHE)
        download_stop = threading.Event()

        def _watch_download(label):
            while not download_stop.is_set():
                try:
                    # Ищем .incomplete файлы среди blobs/ HF-кеша
                    biggest = 0
                    for inc in cache_dir.rglob('*.incomplete'):
                        try:
                            sz = inc.stat().st_size
                            if sz > biggest:
                                biggest = sz
                        except OSError:
                            continue
                    if biggest > 0:
                        mb = biggest / (1024 * 1024)
                        _publish_progress(extra={'message': f'{label} (скачано {mb:.1f} МБ из ~70 МБ)'})
                except Exception:
                    pass
                download_stop.wait(2.0)  # каждые 2 сек

        last_shard = min(78, start_shard + shards_to_pull)
        for shard_idx in range(start_shard, last_shard):
            if len(out) >= limit:
                break
            shard_name = f'data/train-{shard_idx:05d}-of-00078.parquet'
            self.stdout.write(f'  → шард {shard_idx} (до {last_shard - 1}): {shard_name}')
            shard_label = f'Скачиваю шард {shard_idx}/{last_shard - 1}…'
            _publish_progress(extra={'message': shard_label})

            # Зачистка зависших .incomplete от предыдущих failed-runs — иначе
            # hf_hub_download иногда зависает, пытаясь продолжить с битого места.
            if not opts.get('local_only'):
                try:
                    for inc in cache_dir.rglob('*.incomplete'):
                        try:
                            inc.unlink()
                        except OSError:
                            pass
                except Exception:
                    pass

            # Стартуем watcher-поток до начала загрузки, останавливаем после.
            download_stop.clear()
            watcher = None
            if not opts.get('local_only'):
                watcher = threading.Thread(target=_watch_download, args=(shard_label,), daemon=True)
                watcher.start()

            parquet_path = None
            local_cache_dir = DATASET_DIR / 'hf_cache' / spec['hf_id'].replace('/', '__')
            local_cache_dir.mkdir(parents=True, exist_ok=True)
            local_parquet = local_cache_dir / Path(shard_name).name
            if local_parquet.exists() and local_parquet.stat().st_size > 0:
                parquet_path = str(local_parquet)
                self.stdout.write(f'  cache hit: {local_parquet}')
            elif opts.get('local_only'):
                download_stop.set()
                self.stdout.write(
                    self.style.WARNING(f'  cache miss: {local_parquet}; --local-only не открывает сеть.')
                )
                continue
            else:
                try:
                    parquet_path = self._download_hf_parquet_requests(
                        spec=spec,
                        shard_name=shard_name,
                        target_path=local_parquet,
                        token=hf_token,
                        deadline_seconds=int(opts.get('download_deadline') or 120),
                        progress=lambda payload: _publish_progress(extra=payload),
                    )
                except Exception as exc:
                    download_stop.set()
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ⚠ шард {shard_idx + 1} не скачан: {type(exc).__name__}: {str(exc)[:180]}'
                        )
                    )
                    continue

            download_stop.set()

            try:
                pf = pq.ParquetFile(parquet_path)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'  ⚠ шард {shard_idx + 1} не открылся: {exc}'))
                continue

            # Читаем все колонки КРОМЕ бинарных image (PNG/JPEG): их страницы в
            # этом датасете повреждены и роняли iter_batches, а для парсинга схемы
            # они не нужны (берём schematic/json/yaml). Без image шард читается весь.
            all_cols = list(pf.schema_arrow.names)
            read_cols = [c for c in all_cols if c.lower() not in ('image', 'png', 'jpeg', 'thumbnail')]
            if shard_idx == start_shard:
                self.stdout.write(
                    f'  parquet: {pf.metadata.num_rows} строк, колонки: {all_cols} '
                    f'(читаю без бинарных: {read_cols})'
                )
            _publish_progress(extra={'message': f'Распаковка шарда {shard_idx}/{last_shard - 1}…'})

            for batch in _safe_iter_batches(pf, self, shard_idx, columns=read_cols):
                if len(out) >= limit:
                    break
                batch_dict = batch.to_pydict()
                n_in_batch = len(next(iter(batch_dict.values())))
                for i in range(n_in_batch):
                    if len(out) >= limit:
                        break
                    processed += 1
                    if processed % 10 == 0:
                        _publish_progress()
                    if processed % 100 == 0:
                        self.stdout.write(
                            f'  обработано {processed}, импортировано {len(out)}, '
                            f'пропущено {skipped} (decode_errors={decode_errors})'
                        )

                    row = {k: batch_dict[k][i] for k in batch_dict.keys()}
                    if not first_row_dumped:
                        diag_keys = []
                        for k, v in row.items():
                            kind = type(v).__name__
                            size = len(v) if isinstance(v, (bytes, str, list, dict)) else '-'
                            diag_keys.append(f'{k}({kind},sz={size})')
                        self.stdout.write(f'  первая строка: {", ".join(diag_keys)}')
                        first_row_dumped = True

                    scheme_data = self._row_to_scheme_data(row, TEXT_KEYS, JSON_KEYS, import_kicad_sexpr)
                    if not scheme_data or not scheme_data.get('components'):
                        skipped += 1
                        continue

                    n = len(scheme_data['components'])
                    if n < opts['min_components'] or n > opts['max_components']:
                        skipped += 1
                        continue

                    scheme_data['__training_metadata'] = {
                        'source_ids': [],
                        'dataset_source_ids': [f'hf:{spec["hf_id"]}'],
                        'source_topics': self._extract_topics(row),
                        'teacher_rules': [],
                        'evidence_kind': 'external_curated',
                        'dataset_source': 'open_schematics',
                        'license': spec['license'],
                        'attribution': spec['attribution'],
                    }
                    out.append(scheme_data)

        _publish_progress(
            state='running', extra={'message': f'Финализация: импортировано {len(out)}, пропущено {skipped}'}
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'OK: импортировано {len(out)} схем (обработано {processed}, пропущено {skipped})'
            )
        )
        return out

    def _download_hf_parquet_requests(
        self,
        *,
        spec,
        shard_name,
        target_path: Path,
        token=None,
        deadline_seconds: int = 120,
        progress=None,
    ):
        """Download one HuggingFace dataset shard with bounded requests timeouts."""
        try:
            import requests
        except ImportError as exc:
            raise CommandError('requests is required for robust dataset download') from exc

        url = f'https://huggingface.co/datasets/{spec["hf_id"]}/resolve/main/{shard_name}'
        headers = {}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(target_path.suffix + '.part')
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

        if progress:
            progress({'stage': 'download', 'message': f'Скачиваю {shard_name} через requests…'})
        started_at = time.time()
        with requests.get(
            url, headers=headers, stream=True, timeout=(15, 30), allow_redirects=True
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get('content-length') or 0)
            downloaded = 0
            last_update = time.time()
            with tmp_path.open('wb') as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if time.time() - started_at > max(10, int(deadline_seconds)):
                        raise TimeoutError(
                            f'Download deadline exceeded: {deadline_seconds}s for {shard_name}'
                        )
                    if not chunk:
                        continue
                    handle.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if progress and now - last_update >= 1.5:
                        mb = downloaded / (1024 * 1024)
                        payload = {
                            'stage': 'download',
                            'downloaded_mb': round(mb, 1),
                            'message': f'Скачано {mb:.1f} МБ',
                        }
                        if total:
                            payload['download_total_mb'] = round(total / (1024 * 1024), 1)
                            payload['message'] += f' из {payload["download_total_mb"]:.1f} МБ'
                        progress(payload)
                        last_update = now
        if tmp_path.stat().st_size <= 0:
            raise CommandError(f'Downloaded empty shard: {shard_name}')
        tmp_path.replace(target_path)
        if progress:
            progress(
                {
                    'stage': 'downloaded',
                    'downloaded_mb': round(target_path.stat().st_size / (1024 * 1024), 1),
                    'message': f'Шард сохранен: {target_path.name}',
                }
            )
        return str(target_path)

    def _row_to_scheme_data(self, row, text_keys, json_keys, kicad_parser):
        """Превращает row из parquet в нашу scheme_data dict, пробуя:
        1) Известные JSON-поля (тогда сразу json.loads).
        2) Известные text-поля → парсим как KiCad sexpr.
        3) ЛЮБОЕ str/bytes поле длиной >100 — пробуем KiCad-парсер.
        Возвращает None если ничего не сработало.
        """
        # Шаг 1: JSON-поля
        for key in json_keys:
            val = row.get(key)
            if isinstance(val, (str, bytes)):
                try:
                    text = val.decode('utf-8', errors='ignore') if isinstance(val, bytes) else val
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and parsed.get('components'):
                        return parsed
                except Exception:
                    pass

        # Шаг 2: известные text-поля → KiCad sexpr
        for key in text_keys:
            val = row.get(key)
            text = None
            if isinstance(val, bytes):
                text = val.decode('utf-8', errors='ignore')
            elif isinstance(val, str):
                text = val
            if text and len(text) > 50:
                try:
                    result = kicad_parser(text)
                    sd = result.get('scheme_data') if isinstance(result, dict) else None
                    if sd and sd.get('components'):
                        return sd
                except Exception:
                    pass

        # Шаг 3: любое длинное text-поле (fallback)
        for key, val in row.items():
            if key in text_keys or key in json_keys:
                continue
            text = None
            if isinstance(val, bytes):
                # Пропускаем PNG/JPEG бинари
                if val[:4] in (b'\x89PNG', b'\xff\xd8\xff\xe0', b'\xff\xd8\xff\xe1'):
                    continue
                text = val.decode('utf-8', errors='ignore')
            elif isinstance(val, str):
                text = val
            if text and len(text) > 200 and '(' in text[:100]:
                # Похоже на sexpr (открывающие скобки в начале)
                try:
                    result = kicad_parser(text)
                    sd = result.get('scheme_data') if isinstance(result, dict) else None
                    if sd and sd.get('components'):
                        return sd
                except Exception:
                    pass

        return None

    def _import_spice_dir(self, opts):
        """Локальная директория с SPICE-netlist'ами (.cir/.sp/.asc)."""
        path = opts.get('path')
        if not path:
            raise CommandError('--path обязателен для --source spice_dir')
        root = Path(path)
        if not root.exists() or not root.is_dir():
            raise CommandError(f'Путь не существует: {root}')

        from Dolg_APP.services.cad_import import import_spice_netlist

        files = list(root.rglob('*.cir')) + list(root.rglob('*.sp')) + list(root.rglob('*.asc'))
        self.stdout.write(f'Найдено файлов: {len(files)}')

        limit = max(1, int(opts['limit']))
        out = []
        skipped = 0
        for f in files[: limit * 2]:
            if len(out) >= limit:
                break
            try:
                text = f.read_text(encoding='utf-8', errors='ignore')
                result = import_spice_netlist(text)
                sd = result.get('scheme_data')
                if not sd or not sd.get('components'):
                    skipped += 1
                    continue
                n = len(sd['components'])
                if n < opts['min_components'] or n > opts['max_components']:
                    skipped += 1
                    continue
                sd['__training_metadata'] = {
                    'source_ids': [],
                    'dataset_source_ids': [f'local:{f.relative_to(root)}'],
                    'source_topics': [],
                    'teacher_rules': [],
                    'evidence_kind': 'external_spice',
                    'dataset_source': 'spice_dir',
                    'license': SUPPORTED_SOURCES['spice_dir']['license'],
                    'attribution': str(f.relative_to(root)),
                }
                out.append(sd)
            except Exception:
                skipped += 1
        self.stdout.write(
            self.style.SUCCESS(f'✓ Импортировано {len(out)} SPICE-netlists, пропущено {skipped}')
        )
        return out

    # ----- Helpers -------------------------------------------------------

    def _extract_topics(self, row):
        topics = []
        if isinstance(row.get('description'), str):
            for tag in row['description'].split()[:8]:
                if 2 < len(tag) < 30:
                    topics.append(tag.lower())
        return topics[:10]

    def _persist_to_db(self, schemes, source, spec):
        try:
            from Dolg_APP.models import AITrainingExample
        except ImportError:
            self.stdout.write(self.style.WARNING('AITrainingExample не найден — пропускаю --persist.'))
            return
        from django.utils import timezone

        from Dolg_APP.ml.neural import (
            _detect_teacher_topology,
            _next_component_teacher,
            _risk_teacher,
            scheme_to_features,
        )

        created = 0
        updated = 0
        for index, s in enumerate(schemes, start=1):
            meta = s.get('__training_metadata') or {}
            try:
                scheme_copy = json.loads(json.dumps(s, ensure_ascii=False))
                scheme_copy.pop('__training_metadata', None)
                topology = _detect_teacher_topology(scheme_copy)
                risk_score = round(float(_risk_teacher(scheme_copy)), 4)
                next_component = _next_component_teacher(scheme_copy)
                prompt = (
                    f'Разбери импортированную схему из датасета {source} #{index}: '
                    f'компонентов {len(scheme_copy.get("components") or [])}, '
                    f'соединений {len(scheme_copy.get("connections") or [])}.'
                )
                target = '\n'.join(
                    [
                        f'topology={topology}',
                        f'risk_score={risk_score}',
                        f'next_component={next_component}',
                        f'dataset_source={source}',
                        f'license={spec.get("license")}',
                    ]
                )
                features = {
                    'source': 'external_dataset',
                    'evidence_kind': meta.get('evidence_kind') or 'external_curated',
                    'dataset_source': meta.get('dataset_source') or source,
                    'dataset_source_ids': meta.get('dataset_source_ids') or [],
                    'external_index': index,
                    'license': meta.get('license') or spec.get('license'),
                    'attribution': meta.get('attribution') or spec.get('attribution'),
                    'scheme_data': scheme_copy,
                    'feature_vector': scheme_to_features(scheme_copy),
                    'topology': topology,
                    'risk_score': risk_score,
                    'next_component': next_component,
                    'component_count': len(scheme_copy.get('components') or []),
                    'connection_count': len(scheme_copy.get('connections') or []),
                    'source_ids': meta.get('source_ids') or [],
                    'source_topics': meta.get('source_topics') or [],
                    'teacher_rules': meta.get('teacher_rules') or [],
                    'imported_at': timezone.now().isoformat(),
                }
                existing = AITrainingExample.objects.filter(
                    kind='review_hint',
                    features__source='external_dataset',
                    features__dataset_source=source,
                    features__external_index=index,
                ).first()
                if existing:
                    existing.prompt = prompt
                    existing.target = target
                    existing.features = features
                    existing.is_validated = True
                    existing.save(update_fields=['prompt', 'target', 'features', 'is_validated'])
                    updated += 1
                else:
                    AITrainingExample.objects.create(
                        kind='review_hint',
                        prompt=prompt,
                        target=target,
                        features=features,
                        is_validated=True,
                    )
                    created += 1
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'  persist failed: {exc}'))
        self.stdout.write(
            self.style.SUCCESS(f'Persisted to AITrainingExample: created={created}, updated={updated}')
        )
        return

        created = 0
        for s in schemes:
            meta = s.get('__training_metadata') or {}
            try:
                AITrainingExample.objects.update_or_create(
                    name=f'{source}#{created + 1}',
                    defaults={
                        'features': {
                            'scheme_data': s,
                            'source_ids': meta.get('source_ids') or [],
                            'source_topics': meta.get('source_topics') or [],
                            'teacher_rules': meta.get('teacher_rules') or [],
                            'evidence_kind': meta.get('evidence_kind') or 'external_curated',
                        },
                        'is_validated': True,
                        'created_at': timezone.now(),
                    },
                )
                created += 1
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f'  ⚠ persist failed: {exc}'))
        self.stdout.write(self.style.SUCCESS(f'✓ Persisted to AITrainingExample: {created}'))

    def _persist_to_projects(self, schemes, source, spec, *, min_quality=60):
        """Create demo projects from good imported schemes."""
        from django.contrib.auth import get_user_model
        from django.utils.text import slugify

        from Dolg_APP.models import ProjectEvent, SchematicProject
        from Dolg_APP.services.ai_training import score_scheme_for_training

        User = get_user_model()
        owner = (
            User.objects.filter(is_superuser=True).order_by('id').first()
            or User.objects.filter(is_staff=True).order_by('id').first()
        )
        if owner is None:
            owner, _ = User.objects.get_or_create(
                username='ai_import_bot',
                defaults={'email': 'ai-import-bot@local.invalid', 'is_active': True},
            )
            owner.set_unusable_password()
            owner.save(update_fields=['password'])

        category_map = {
            'led_indicator': 'led',
            'voltage_divider': 'power',
            'resistive_network': 'power',
            'diode_node': 'led',
        }
        created = 0
        updated = 0
        skipped = 0
        for index, s in enumerate(schemes, start=1):
            scheme_copy = json.loads(json.dumps(s, ensure_ascii=False))
            meta = scheme_copy.pop('__training_metadata', {}) if isinstance(scheme_copy, dict) else {}
            if not isinstance(scheme_copy, dict) or not scheme_copy.get('components'):
                skipped += 1
                continue
            score = score_scheme_for_training(scheme_copy)
            if score['quality_score'] < int(min_quality):
                skipped += 1
                continue
            safe_source = slugify(source) or 'dataset'
            name = f'AI dataset: {source} #{index}'
            description = (
                f'Импортировано из датасета {source}. '
                f'Тип: {score["family"]}; сложность: {score["complexity_label"]} '
                f'({score["complexity_score"]}/100); качество: {score["quality_label"]} '
                f'({score["quality_score"]}/100). '
                f'Лицензия/атрибуция: {meta.get("license") or spec.get("license")} / '
                f'{meta.get("attribution") or spec.get("attribution")}'
            )
            project, was_created = SchematicProject.all_objects.update_or_create(
                user=owner,
                name=name,
                defaults={
                    'description': description,
                    'category': category_map.get(score['family'], 'other'),
                    'status': 'completed',
                    'difficulty': score['complexity_label']
                    if score['complexity_label'] in {'basic', 'medium', 'advanced'}
                    else 'basic',
                    'is_demo': True,
                    'visibility': 'public',
                    'approval_state': 'approved',
                    'scheme_data': scheme_copy,
                    'deleted_at': None,
                },
            )
            ProjectEvent.log(
                project=project,
                user=owner,
                event_type='import_finished',
                payload={
                    'source': source,
                    'dataset_key': f'{safe_source}:{index}',
                    'quality_score': score['quality_score'],
                    'complexity_score': score['complexity_score'],
                    'scheme_family': score['family'],
                },
            )
            created += int(was_created)
            updated += int(not was_created)
        self.stdout.write(
            self.style.SUCCESS(
                f'Persisted to SchematicProject demos: created={created}, updated={updated}, skipped={skipped}'
            )
        )
