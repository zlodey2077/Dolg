"""MCP-сервер: YouTube → транскрипт/конспект-сырьё (локально, без облака).

Ставится в ~/.claude/mcp.json как headroom (.venv python + путь к этому файлу).
Тонкая обёртка над scripts/yt_transcript.py: тот же движок (youtube-transcript-api
+ yt-dlp фолбэк). Транспорт — stdio (FastMCP), поэтому НЕ печатаем в stdout сами.

Инструменты:
- get_youtube_transcript(url, languages) → читаемый текст (шапка+главы+таймкоды);
- list_youtube_languages(url) → какие дорожки субтитров доступны.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Импорт ядра из соседнего файла независимо от cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yt_transcript as engine
from mcp.server.fastmcp import FastMCP

mcp = FastMCP('yt-transcript')


@mcp.tool()
def get_youtube_transcript(url: str, languages: list[str] | None = None) -> str:
    """Транскрипт YouTube-ролика + метаданные как читаемый текст.

    url: ссылка на YouTube или 11-символьный video id.
    languages: предпочтительные языки субтитров по убыванию (по умолчанию ru, en).
    Возвращает заголовок/канал/длительность/главы и транскрипт с таймкодами,
    либо строку с [ОШИБКА] если субтитров нет.
    """
    result = engine.get_transcript(url, languages or engine.PREF_LANGS)
    return engine.render_text(result)


@mcp.tool()
def list_youtube_languages(url: str) -> str:
    """Список доступных дорожек субтитров (ручные + авто) для ролика."""
    import yt_dlp

    opts = {'quiet': True, 'skip_download': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        return f'[ОШИБКА] {exc}'
    manual = sorted((info.get('subtitles') or {}).keys())
    auto = sorted((info.get('automatic_captions') or {}).keys())
    return f'Ручные: {", ".join(manual) or "—"}\nАвто: {", ".join(auto[:40]) or "—"}'


if __name__ == '__main__':
    mcp.run()
