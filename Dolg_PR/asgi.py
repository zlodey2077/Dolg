"""ASGI config для DOLG.

Маршрутизирует HTTP-запросы через стандартный Django ASGI app, а WebSocket —
через Channels routing (`Dolg_APP.routing.websocket_urlpatterns`). Для
аутентификации WebSocket используем AuthMiddlewareStack — он подкладывает
request.user из session-cookie. Origin-check защищает от подключений с чужого
домена (CSRF-аналог для WS).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')

# Сначала инициализируем Django (нужно для импорта моделей в consumers).
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

from Dolg_APP.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
    }
)
