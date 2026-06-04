"""WebSocket URL routing для DOLG.

Используется в Dolg_PR/asgi.py через URLRouter(websocket_urlpatterns).
HTTP-маршруты остаются в Dolg_APP/urls.py.
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    # Публичный Q&A чат — один топик = одна WS-комната.
    path('ws/chat/topic/<int:topic_id>/', consumers.ChatTopicConsumer.as_asgi()),
    # Enterprise приватные каналы — комната по organization slug + conv id.
    path(
        'ws/orgs/<slug:org_slug>/conversations/<int:conv_id>/',
        consumers.OrgConversationConsumer.as_asgi(),
    ),
    # Сеанс проектирования — progress/events для схемы, симуляций и review.
    path('ws/project/<int:project_id>/', consumers.ProjectConsumer.as_asgi()),
]
