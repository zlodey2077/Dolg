"""YouTube → транскрипт + метаданные для конспектов проекта (локально, без облака).

Движок: youtube-transcript-api (быстрые субтитры) с фолбэком на yt-dlp (метаданные +
авто-сабы json3, работает там, где API не отдаёт). Вывод — чистый текст с таймкодами
и главами, либо --json. Это ядро: и CLI (агент зовёт через Bash), и MCP-сервер
(scripts/yt_mcp_server.py) используют одни и те же функции.

    .venv\\Scripts\\python.exe scripts/yt_transcript.py "https://youtu.be/XXXX" --lang ru en
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

# UTF-8 вывод: на рус. Windows консоль = cp1251, иначе UnicodeEncodeError на кириллице.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

PREF_LANGS = ['ru', 'en']


def extract_video_id(url: str) -> str | None:
    url = (url or '').strip()
    if re.fullmatch(r'[0-9A-Za-z_-]{11}', url):
        return url
    m = re.search(r'(?:v=|/shorts/|youtu\.be/|/embed/|/v/|/live/)([0-9A-Za-z_-]{11})', url)
    return m.group(1) if m else None


def fetch_via_api(video_id: str, langs: list[str]) -> list[dict]:
    """youtube-transcript-api v1.x (instance .fetch). Бросает, если сабов нет."""
    from youtube_transcript_api import YouTubeTranscriptApi

    fetched = YouTubeTranscriptApi().fetch(video_id, languages=langs)
    return [{'start': float(s.start), 'dur': float(s.duration), 'text': s.text} for s in fetched]


def metadata_via_ytdlp(url: str) -> dict:
    """Метаданные ролика через yt-dlp (без скачивания)."""
    import yt_dlp

    opts = {'quiet': True, 'skip_download': True, 'no_warnings': True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        'id': info.get('id'),
        'title': info.get('title'),
        'uploader': info.get('uploader') or info.get('channel'),
        'duration': info.get('duration'),
        'webpage_url': info.get('webpage_url') or url,
        'chapters': [
            {'start': c.get('start_time'), 'title': c.get('title')} for c in (info.get('chapters') or [])
        ],
    }


def fetch_via_ytdlp(url: str, langs: list[str]) -> list[dict]:
    """Фолбэк: достаём субтитры (manual→auto) в формате json3 и парсим в сниппеты."""
    import yt_dlp

    opts = {
        'quiet': True,
        'skip_download': True,
        'no_warnings': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': langs,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    subs = {**(info.get('subtitles') or {}), **(info.get('automatic_captions') or {})}
    chosen = None
    for lg in langs:
        for key, tracks in subs.items():
            if key == lg or key.startswith(lg + '-') or key.startswith(lg):
                chosen = tracks
                break
        if chosen:
            break
    if not chosen:
        return []
    url3 = next((f['url'] for f in chosen if f.get('ext') == 'json3'), chosen[0]['url'])
    raw = urllib.request.urlopen(url3, timeout=25).read().decode('utf-8', errors='replace')
    data = json.loads(raw)
    snips = []
    for ev in data.get('events') or []:
        if 'segs' not in ev:
            continue
        text = ''.join(s.get('utf8', '') for s in ev['segs']).strip()
        if not text:
            continue
        snips.append(
            {'start': ev.get('tStartMs', 0) / 1000.0, 'dur': ev.get('dDurationMs', 0) / 1000.0, 'text': text}
        )
    return snips


def get_transcript(url: str, langs: list[str] | None = None) -> dict:
    """Главная точка входа: {ok, meta, snippets, source} либо {ok:False, error}."""
    langs = langs or PREF_LANGS
    vid = extract_video_id(url)
    if not vid:
        return {'ok': False, 'error': f'не распознан YouTube-URL/ID: {url!r}'}
    meta = {}
    try:
        meta = metadata_via_ytdlp(url)
    except Exception as exc:
        meta = {'id': vid, 'title': None, 'note': f'metadata недоступна: {exc}'}
    source = 'youtube-transcript-api'
    try:
        snippets = fetch_via_api(vid, langs)
    except Exception:
        source = 'yt-dlp (auto-subs)'
        try:
            snippets = fetch_via_ytdlp(url, langs)
        except Exception as exc:
            return {'ok': False, 'error': f'субтитры недоступны (нет капшенов?): {exc}', 'meta': meta}
    if not snippets:
        return {'ok': False, 'error': 'субтитры пустые/недоступны', 'meta': meta}
    return {'ok': True, 'meta': meta, 'snippets': snippets, 'source': source}


def _fmt_ts(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f'{h:d}:{m:02d}:{s:02d}' if h else f'{m:d}:{s:02d}'


def render_text(result: dict, stamp_every: int = 30) -> str:
    """Читаемый вид: шапка + главы + транскрипт с таймкодами раз в ~stamp_every сек."""
    if not result.get('ok'):
        return f'[ОШИБКА] {result.get("error")}'
    meta = result.get('meta') or {}
    lines = []
    if meta.get('title'):
        lines.append(f'# {meta["title"]}')
    bits = []
    if meta.get('uploader'):
        bits.append(f'канал: {meta["uploader"]}')
    if meta.get('duration'):
        bits.append(f'длительность: {_fmt_ts(meta["duration"])}')
    bits.append(f'источник субтитров: {result.get("source")}')
    if meta.get('webpage_url'):
        bits.append(meta['webpage_url'])
    lines.append(' · '.join(bits))
    if meta.get('chapters'):
        lines.append('\n## Главы')
        for ch in meta['chapters']:
            lines.append(f'  [{_fmt_ts(ch.get("start") or 0)}] {ch.get("title")}')
    lines.append('\n## Транскрипт')
    next_stamp = 0.0
    buf = []
    for snip in result['snippets']:
        if snip['start'] >= next_stamp:
            if buf:
                lines.append(' '.join(buf))
                buf = []
            lines.append(f'[{_fmt_ts(snip["start"])}]')
            next_stamp = snip['start'] + stamp_every
        buf.append(snip['text'].replace('\n', ' ').strip())
    if buf:
        lines.append(' '.join(buf))
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description='YouTube → транскрипт + метаданные')
    ap.add_argument('url', help='YouTube URL или video id')
    ap.add_argument('--lang', nargs='+', default=PREF_LANGS, help='предпочтительные языки (по убыванию)')
    ap.add_argument('--json', action='store_true', help='вывести JSON вместо текста')
    ap.add_argument('--stamp-every', type=int, default=30, help='таймкод раз в N сек (текстовый режим)')
    args = ap.parse_args()
    result = get_transcript(args.url, args.lang)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result, stamp_every=args.stamp_every))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
