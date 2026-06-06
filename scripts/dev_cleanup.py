"""Один рубильник чистоты dev-окружения DOLG.

Убивает зависшие dev-процессы (runserver-зомби, Playwright-chromium) и
освобождает порт 8000 — чтобы не копить зомби и не грузить машину. Не трогает
обычный Chrome юзера (Playwright-браузер опознаётся по пути ms-playwright).

  python scripts/dev_cleanup.py            убить runserver + playwright chromium + порт 8000
  python scripts/dev_cleanup.py --list     только показать (dry-run)
  python scripts/dev_cleanup.py --proxy    дополнительно остановить headroom proxy (:8787)
"""

import sys

try:
    import psutil
except ImportError:
    print('psutil не установлен: .venv/Scripts/python.exe -m pip install psutil')
    sys.exit(1)

LIST = '--list' in sys.argv
KILL_PROXY = '--proxy' in sys.argv


def _cmdline(proc):
    try:
        return ' '.join(proc.cmdline())
    except Exception:
        return ''


def _classify(proc, cl):
    low = cl.lower()
    name = (proc.name() or '').lower()
    # Только реальные python-процессы runserver — НЕ bash/cmd-обёртки, которые
    # их запускали (иначе можно убить shell-раннеры Claude Code и сломать сессию).
    if 'python' in name and 'manage.py' in low and 'runserver' in low:
        return 'django runserver'
    # Playwright-браузер: путь содержит ms-playwright (НЕ обычный Chrome юзера).
    if 'ms-playwright' in low and ('chrome' in name or 'headless' in low or 'chromium' in low):
        return 'playwright chromium'
    if KILL_PROXY and 'headroom' in low and 'proxy' in low:
        return 'headroom proxy'
    return None


def main():
    me = psutil.Process().pid
    parent = psutil.Process().ppid()
    targets = []
    for proc in psutil.process_iter():
        if proc.pid in (me, parent):
            continue
        try:
            cl = _cmdline(proc)
            reason = _classify(proc, cl)
        except Exception:
            continue
        if reason:
            targets.append((proc, reason, cl))

    if not targets:
        print('чисто — нечего убивать')
        return

    for proc, reason, cl in targets:
        tag = f'[{reason}] PID {proc.pid}: {cl[:80]}'
        if LIST:
            print('  ' + tag)
        else:
            try:
                proc.terminate()
                print('убит ' + tag)
            except Exception as exc:
                print(f'не смог убить PID {proc.pid}: {exc}')

    if not LIST:
        gone, alive = psutil.wait_procs([t[0] for t in targets], timeout=3)
        for proc in alive:
            try:
                proc.kill()
            except Exception:
                pass
        print(f'готово: завершено {len(targets)} процесс(ов)')


if __name__ == '__main__':
    main()
