"""WebSocket consumers для DOLG real-time чата.

Архитектура:
- Один топик/беседа = одна channel-group ("chat-topic-<id>" / "org-conv-<id>")
- View'ы при создании reply/message делают group_send (см. chat_views.py)
- Consumer получает event и пушит в socket клиенту

Каждый client-side WS — получает только новые сообщения комнаты, в которую
подписался. Polling-endpoints оставлены как fallback (если WS не подключился).
"""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from . import comments_render
from .models import ChatReply, ChatTopic, OrgConversation, OrgConversationMessage, SchematicProject
from .org_permissions import user_can

CHAT_TOPIC_GROUP = 'chat-topic-{topic_id}'
ORG_CONV_GROUP = 'org-conv-{conv_id}'
PROJECT_GROUP = 'project-{project_id}'


# ────────────────────────────────────────────────────────────────────────
# Public Q&A
# ────────────────────────────────────────────────────────────────────────

class ChatTopicConsumer(AsyncJsonWebsocketConsumer):
    """Подписка на новые reply'и одного публичного топика.

    Guest может подключиться (читать обновления), создавать reply'и — нет
    (это идёт через HTTP POST, проверка login_required). Consumer только
    транслирует, не валидирует write-операции.
    """

    async def connect(self):
        self.topic_id = self.scope['url_route']['kwargs']['topic_id']
        exists = await self._topic_exists(self.topic_id)
        if not exists:
            await self.close(code=4004)
            return
        self.group_name = CHAT_TOPIC_GROUP.format(topic_id=self.topic_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({'type': 'connected', 'topic_id': self.topic_id})

    async def disconnect(self, code):
        group = getattr(self, 'group_name', None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        """Клиент может слать ping для keep-alive (некоторые прокси режут
        idle-соединения через 30-60 сек). Игнорируем всё остальное —
        write-операции идут через HTTP."""
        msg_type = content.get('type', '')
        if msg_type == 'ping':
            await self.send_json({'type': 'pong'})

    async def chat_reply_created(self, event):
        """Хендлер group_send-события `type: chat.reply.created`. Пушит
        пришедший reply подписчикам комнаты."""
        await self.send_json({'type': 'reply.created', 'reply': event['reply']})

    @database_sync_to_async
    def _topic_exists(self, topic_id):
        return ChatTopic.objects.filter(pk=topic_id).exists()


# ────────────────────────────────────────────────────────────────────────
# Org приватные беседы (Enterprise)
# ────────────────────────────────────────────────────────────────────────

class OrgConversationConsumer(AsyncJsonWebsocketConsumer):
    """Подписка на новые сообщения приватного канала команды.

    Доступ: только member org с правом `org.chat.read`. Если user не
    member или org/conv не существуют — close с кодом 4003.
    """

    async def connect(self):
        self.org_slug = self.scope['url_route']['kwargs']['org_slug']
        self.conv_id = self.scope['url_route']['kwargs']['conv_id']
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=4001)   # 4001 = unauthorized
            return

        allowed = await self._check_access(user, self.org_slug, self.conv_id)
        if not allowed:
            await self.close(code=4003)   # 4003 = forbidden / not found
            return

        self.group_name = ORG_CONV_GROUP.format(conv_id=self.conv_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            'type': 'connected',
            'org_slug': self.org_slug,
            'conv_id': self.conv_id,
        })

    async def disconnect(self, code):
        group = getattr(self, 'group_name', None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    async def org_conv_message_created(self, event):
        """Хендлер для типа `type: org.conv.message.created`."""
        await self.send_json({'type': 'message.created', 'message': event['message']})

    @database_sync_to_async
    def _check_access(self, user, org_slug, conv_id):
        try:
            conv = OrgConversation.objects.select_related('organization').get(
                pk=conv_id, organization__slug=org_slug,
            )
        except OrgConversation.DoesNotExist:
            return False
        return user_can(user, conv.organization, 'org.chat.read')


# ────────────────────────────────────────────────────────────────────────
# Project session events
# ────────────────────────────────────────────────────────────────────────

class ProjectConsumer(AsyncJsonWebsocketConsumer):
    """Push-канал одного сеанса проектирования.

    HTTP остается источником записи. WebSocket только сообщает UI о новых
    событиях: сохранение схемы, симуляция, измерение, review, BOM/import.
    """

    async def connect(self):
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=4001)
            return
        allowed = await self._check_access(user, self.project_id)
        if not allowed:
            await self.close(code=4003)
            return
        self.group_name = PROJECT_GROUP.format(project_id=self.project_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({'type': 'connected', 'project_id': self.project_id})

    async def disconnect(self, code):
        group = getattr(self, 'group_name', None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    async def project_event(self, event):
        await self.send_json({'type': 'project.event', 'event': event.get('event') or {}})

    @database_sync_to_async
    def _check_access(self, user, project_id):
        try:
            project = SchematicProject.objects.select_related('organization').get(pk=project_id)
        except SchematicProject.DoesNotExist:
            return False
        if project.is_demo or project.user_id == user.id or project.visibility == 'public':
            return True
        return bool(
            project.visibility == 'team'
            and project.organization_id
            and project.organization.has_member(user)
        )


# ────────────────────────────────────────────────────────────────────────
# Helpers для view'ев (вызывается из HTTP-views через async_to_sync)
# ────────────────────────────────────────────────────────────────────────

def serialize_reply_for_ws(reply: ChatReply, *, is_pro_viewer: bool) -> dict:
    """Сериализация ChatReply для WS-broadcast'а. Эквивалент _reply_to_dict
    из chat_views, чтобы клиент мог отрисовать сообщение тем же кодом."""
    return {
        'id': reply.id,
        'parent_id': reply.parent_id,
        'author': reply.author.username if reply.author else 'удалённый',
        'body_html': comments_render.render(reply.body, rich=is_pro_viewer),
        'is_accepted_answer': reply.is_accepted_answer,
        'created_at': reply.created_at.isoformat(),
    }


def serialize_org_message_for_ws(msg: OrgConversationMessage) -> dict:
    return {
        'id': msg.id,
        'parent_id': msg.parent_id,
        'author': msg.author.username if msg.author else 'удалённый',
        'body_html': comments_render.render(msg.body, rich=True),
        'created_at': msg.created_at.isoformat(),
    }
