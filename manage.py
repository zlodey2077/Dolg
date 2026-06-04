#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')
    # 2026-06-05 startup-perf: для CLI-команд, не требующих WebSocket
    # (migrate / makemigrations / shell / check / test / collectstatic /
    # createsuperuser / dumpdata / loaddata и т.п.), пропускаем daphne +
    # channels — экономит ~3 сек на cold start (twisted + autobahn eager-imports).
    # runserver, daphne, runworker — нуждаются в ASGI, не скипаем.
    _CLI_SKIP_ASGI = {
        'migrate',
        'makemigrations',
        'check',
        'shell',
        'shell_plus',
        'test',
        'collectstatic',
        'createsuperuser',
        'changepassword',
        'dumpdata',
        'loaddata',
        'showmigrations',
        'sqlmigrate',
        'sqlflush',
        'inspectdb',
        'diffsettings',
        'startapp',
        'startproject',
        'compilemessages',
        'makemessages',
    }
    if len(sys.argv) > 1 and sys.argv[1] in _CLI_SKIP_ASGI:
        os.environ.setdefault('DOLG_SKIP_ASGI', '1')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            'available on your PYTHONPATH environment variable? Did you '
            'forget to activate a virtual environment?'
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
