"""Лёгкий переиспользуемый Playwright-хелпер для проверки UI DOLG.

Заменяет ad-hoc heredoc-скрипты (которые ещё и путь ломали в MSYS). Один
браузер на вызов; либо подключение к persistent-серверу, чтобы НЕ запускать
chromium на каждую проверку.

Примеры:
  # скриншот
  python scripts/dev_shot.py --url http://127.0.0.1:8000/cad/ --out C:/tmp/cad.png

  # добавить класс перед снимком + напечатать computed-style (без скриншота)
  python scripts/dev_shot.py --url .../cad/ --js "document.body.classList.add('cad-fullscreen')" \
      --eval "getComputedStyle(document.querySelector('header')).display"

  # persistent-режим (запускает chromium-сервер ОДИН раз, печатает ws-endpoint):
  python scripts/dev_shot.py --server
  # затем переиспользовать без нового запуска браузера:
  python scripts/dev_shot.py --connect ws://... --url .../cad/ --eval "..."

Зачем: меньше запусков chromium = меньше нагрузка на машину и стабильнее.
"""

import argparse
import time

from playwright.sync_api import sync_playwright


def run(args):
    with sync_playwright() as pw:
        if args.server:
            server = pw.chromium.launch_server(headless=True)
            print('WS_ENDPOINT=' + server.ws_endpoint, flush=True)
            print('persistent chromium запущен. Ctrl+C для остановки.', flush=True)
            try:
                while True:
                    time.sleep(3600)
            except KeyboardInterrupt:
                server.close()
            return

        browser = pw.chromium.connect(args.connect) if args.connect else pw.chromium.launch(headless=True)
        try:
            w, h = (int(x) for x in args.viewport.split('x'))
            page = browser.new_page(viewport={'width': w, 'height': h})
            page.goto(args.url, wait_until='domcontentloaded', timeout=args.timeout * 1000)
            time.sleep(args.wait)
            if args.js:
                page.evaluate(args.js)
                time.sleep(0.6)
            if args.out:
                page.screenshot(path=args.out, full_page=args.full)
                print('saved ' + args.out, flush=True)
            if args.eval:
                print('EVAL=' + repr(page.evaluate(f'(() => ({args.eval}))()')), flush=True)
            page.close()
        finally:
            if not args.connect:
                browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--server', action='store_true', help='запустить persistent chromium-сервер')
    ap.add_argument('--connect', help='ws-endpoint persistent-сервера (реюз браузера)')
    ap.add_argument('--url')
    ap.add_argument('--out', help='путь для скриншота')
    ap.add_argument('--js', help='JS выполнить перед снимком/eval')
    ap.add_argument('--eval', help='JS-выражение, результат напечатать')
    ap.add_argument('--viewport', default='1366x820')
    ap.add_argument('--wait', type=float, default=2.5, help='пауза после загрузки, сек')
    ap.add_argument('--timeout', type=int, default=60, help='таймаут goto, сек')
    ap.add_argument('--full', action='store_true', help='full-page скриншот')
    args = ap.parse_args()
    if not args.server and not args.url:
        ap.error('нужен --url (или --server)')
    run(args)


if __name__ == '__main__':
    main()
