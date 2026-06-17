"""Views для чатов и бесед.

Public Q&A (ChatTopic + ChatReply + ChatReaction) — доступны всем регистрированным.
Org беседы (OrgConversation + OrgConversationMessage) — только для Enterprise members.
Announcement — read-only сайдбар, публикует только staff.

Tier-логика:
- Guest: чат-страницы видит, но не пишет/реагирует.
- Free: 5 топиков + 20 reply в день, plain-text, 👍 only.
- Pro: безлимит, Markdown, любые emoji, pin своих топиков, attach SchematicProject.
- Enterprise: всё Pro + приватные org-беседы.
"""

import json

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from moderation.services import display_body, is_content_available_to, user_is_restricted, visible_queryset

from . import comments_render
from .models import (
    Announcement,
    ChatReaction,
    ChatReply,
    ChatTopic,
    Organization,
    OrgConversation,
    OrgConversationMessage,
    SchematicProject,
)
from .org_permissions import user_can
from .quotas import check_daily_quota, increment_daily
from .services.entitlements import feature_denied_response, has_feature

CHAT_PAGE_SIZE = 20
POLL_LIMIT = 50  # макс сообщений за один polling-запрос


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────


def _is_pro_or_enterprise(user):
    """True если у юзера Pro tier (через личную подписку или org-membership)."""
    return has_feature(user, 'comments_rich')


def _active_announcements(limit=5):
    return Announcement.objects.filter(
        is_published=True,
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))[:limit]


def _render_body(body, *, is_pro):
    """Free → plain-text, Pro/Enterprise → Markdown."""
    return comments_render.render(body, rich=is_pro)


def _topic_to_dict(topic, request_user=None):
    """JSON-сериализация топика (для polling и API-ответов)."""
    return {
        'id': topic.id,
        'title': topic.title,
        'category': topic.category,
        'author': topic.author.username if topic.author else 'удалённый',
        'is_pinned': topic.is_pinned,
        'is_resolved': topic.is_resolved,
        'replies_count': topic.reply_count(),
        'created_at': topic.created_at.isoformat(),
        'last_activity_at': topic.last_activity_at.isoformat(),
    }


def _reply_to_dict(reply, *, is_pro_viewer):
    return {
        'id': reply.id,
        'parent_id': reply.parent_id,
        'author': reply.author.username if reply.author else 'удалённый',
        'body_html': _render_body(display_body(reply), is_pro=is_pro_viewer),
        'is_accepted_answer': reply.is_accepted_answer,
        'moderation_status': reply.moderation_status,
        'created_at': reply.created_at.isoformat(),
    }


# ────────────────────────────────────────────────────────────────────────
# Public Q&A
# ────────────────────────────────────────────────────────────────────────


def chat_list(request):
    """Список топиков с фильтрами по категории и поиском.

    Guest видит топики, но не может создавать новые / реагировать.
    """
    # Явный order_by — annotate(Count) добавляет GROUP BY, что глушит
    # неявный порядок из Meta.ordering и заставляет Paginator варнить о
    # «inconsistent pagination». Дублируем Meta.ordering явно.
    qs = (
        ChatTopic.objects.select_related('author', 'attached_project')
        .annotate(replies_total=Count('replies'))
        .order_by('-is_pinned', '-last_activity_at')
    )
    qs = visible_queryset(qs, request.user)

    category = request.GET.get('category', '').strip()
    if category and category in dict(ChatTopic.CATEGORY_CHOICES):
        qs = qs.filter(category=category)

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(body__icontains=query))

    only_resolved = request.GET.get('resolved') == '1'
    if only_resolved:
        qs = qs.filter(is_resolved=True)

    paginator = Paginator(qs, CHAT_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(
        request,
        'chat/list.html',
        {
            'topics': page_obj,
            'page_obj': page_obj,
            'paginator': paginator,
            'categories': ChatTopic.CATEGORY_CHOICES,
            'active_category': category,
            'query': query,
            'only_resolved': only_resolved,
            'announcements': _active_announcements(),
            'can_post': request.user.is_authenticated,
            'is_pro_viewer': _is_pro_or_enterprise(request.user) if request.user.is_authenticated else False,
        },
    )


def chat_topic_detail(request, topic_id):
    """Просмотр топика и ответов. Инкрементит views_count."""
    topic = get_object_or_404(
        ChatTopic.objects.select_related('author', 'attached_project'),
        pk=topic_id,
    )
    if not is_content_available_to(topic, request.user):
        return HttpResponseForbidden('Топик скрыт модератором.')
    # Атомарный инкремент просмотров — без F() и без save() ради простоты;
    # для дипломного MVP «вид» от каждого refresh'а — приемлемо.
    ChatTopic.objects.filter(pk=topic.pk).update(views_count=topic.views_count + 1)
    topic.views_count += 1

    is_pro_viewer = _is_pro_or_enterprise(request.user) if request.user.is_authenticated else False
    replies = list(
        visible_queryset(topic.replies.select_related('author', 'parent'), request.user).order_by(
            'created_at'
        )
    )

    # Реакции — bulk-агрегация одним SQL вместо N+1.
    # Раньше: 1 query на топик + 1 query на КАЖДЫЙ reply (N+1).
    # Сейчас: 1 query на ВСЕ реакции этого топика и его reply'ев, далее
    # группируем в Python по (target_topic_id, target_reply_id, emoji).
    reply_ids = [r.id for r in replies]
    rx_qs = (
        ChatReaction.objects.filter(Q(target_topic_id=topic.pk) | Q(target_reply_id__in=reply_ids))
        .values('target_topic_id', 'target_reply_id', 'emoji')
        .annotate(c=Count('id'))
    )

    topic_reactions = []
    reply_reactions = {rid: [] for rid in reply_ids}
    for row in rx_qs:
        item = {'emoji': row['emoji'], 'count': row['c']}
        if row['target_topic_id']:
            topic_reactions.append(item)
        elif row['target_reply_id']:
            reply_reactions.setdefault(row['target_reply_id'], []).append(item)
    # Сортируем по count desc внутри каждой группы (как раньше делал _aggregate_reactions).
    topic_reactions.sort(key=lambda x: -x['count'])
    for k in reply_reactions:
        reply_reactions[k].sort(key=lambda x: -x['count'])

    user_pro_projects = []
    if is_pro_viewer:
        user_pro_projects = list(
            SchematicProject.objects.filter(user=request.user, deleted_at__isnull=True).order_by(
                '-updated_at'
            )[:20]
        )

    return render(
        request,
        'chat/topic_detail.html',
        {
            'topic': topic,
            'topic_body_html': _render_body(display_body(topic, request.user), is_pro=is_pro_viewer),
            'replies': replies,
            'rendered_replies': [
                (r, _render_body(display_body(r, request.user), is_pro=is_pro_viewer)) for r in replies
            ],
            'topic_reactions': topic_reactions,
            'reply_reactions': reply_reactions,
            'is_topic_author': request.user.is_authenticated and topic.author_id == request.user.id,
            'is_pro_viewer': is_pro_viewer,
            'can_post': request.user.is_authenticated,
            'user_pro_projects': user_pro_projects,
            'announcements': _active_announcements(),
            'allowed_emojis_free': ['👍'],
            'allowed_emojis_pro': ['👍', '❤', '✅', '🎉', '🤔', '🚀'],
        },
    )


def _aggregate_reactions(qs):
    """[(emoji, count, user_did_react)] — для UI."""
    counts = {}
    for r in qs:
        counts[r.emoji] = counts.get(r.emoji, 0) + 1
    return [{'emoji': e, 'count': c} for e, c in sorted(counts.items(), key=lambda x: -x[1])]


@login_required(login_url='accounts:login')
@require_POST
def chat_topic_create(request):
    """Создать новый топик. Free: 5/день квота. Pro: безлимит."""
    if user_is_restricted(request.user, 'write'):
        return _form_error(
            request,
            'Ваш аккаунт временно ограничен модератором.',
            redirect_to='hello:chat_list',
            status=403,
        )
    allowed, reason = check_daily_quota(request.user, 'chat_topics')
    if not allowed:
        return _form_error(request, reason, redirect_to='hello:chat_list')

    title = (request.POST.get('title') or '').strip()
    body = (request.POST.get('body') or '').strip()
    category = (request.POST.get('category') or 'general').strip()
    if category not in dict(ChatTopic.CATEGORY_CHOICES):
        category = 'general'

    if not title or not body:
        return _form_error(request, 'Заполните заголовок и текст.', redirect_to='hello:chat_list')
    if len(title) > 200:
        return _form_error(
            request, 'Слишком длинный заголовок (макс 200 символов).', redirect_to='hello:chat_list'
        )

    attached_project = None
    is_pro = _is_pro_or_enterprise(request.user)
    project_id = request.POST.get('attached_project_id')
    if project_id and is_pro:
        try:
            attached_project = SchematicProject.objects.get(pk=int(project_id), user=request.user)
        except (SchematicProject.DoesNotExist, ValueError, TypeError):
            attached_project = None

    topic = ChatTopic.objects.create(
        title=title,
        body=body,
        author=request.user,
        category=category,
        attached_project=attached_project,
    )
    increment_daily(request.user, 'chat_topics')
    return redirect('hello:chat_topic_detail', topic_id=topic.id)


@login_required(login_url='accounts:login')
@require_POST
def chat_reply_create(request, topic_id):
    """Добавить ответ в топик. Free: 20/день."""
    if user_is_restricted(request.user, 'write'):
        return _form_error(
            request,
            'Ваш аккаунт временно ограничен модератором.',
            redirect_to='hello:chat_topic_detail',
            topic_id=topic_id,
            status=403,
        )
    topic = get_object_or_404(ChatTopic, pk=topic_id)
    if not is_content_available_to(topic, request.user):
        return JsonResponse({'ok': False, 'error': 'hidden'}, status=403)
    allowed, reason = check_daily_quota(request.user, 'chat_replies')
    if not allowed:
        return _form_error(request, reason, redirect_to='hello:chat_topic_detail', topic_id=topic.id)

    body = (request.POST.get('body') or '').strip()
    if not body:
        return _form_error(request, 'Пустой ответ.', redirect_to='hello:chat_topic_detail', topic_id=topic.id)

    parent = None
    parent_id = request.POST.get('parent_id')
    if parent_id:
        try:
            parent = ChatReply.objects.get(pk=int(parent_id), topic=topic)
        except (ChatReply.DoesNotExist, ValueError, TypeError):
            parent = None

    reply = ChatReply.objects.create(
        topic=topic,
        author=request.user,
        body=body,
        parent=parent,
    )
    # Обновляем last_activity_at для сортировки в списке
    ChatTopic.objects.filter(pk=topic.pk).update(last_activity_at=timezone.now())
    increment_daily(request.user, 'chat_replies')

    # Broadcast в WS-комнату топика. Free/Pro различие render'а body_html
    # подписчик может перерисовать у себя — мы рендерим в Pro-режиме (полный
    # Markdown) и пушим всем. Free-клиент покажет HTML как есть, но Markdown
    # ему не отрисуется (он не Pro). Альтернатива — двойной рендер, но
    # упрощённо: пушим Pro-вариант (Markdown→HTML обработан bleach'ем).
    _broadcast_chat_reply(topic.id, reply)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(
            {
                'ok': True,
                'reply': _reply_to_dict(reply, is_pro_viewer=_is_pro_or_enterprise(request.user)),
            }
        )
    return redirect('hello:chat_topic_detail', topic_id=topic.id)


def _broadcast_chat_reply(topic_id: int, reply: ChatReply):
    """Send reply to chat-topic-<id> WS group. Safe-fail при отсутствии
    channel layer (если кто-то отключил Channels)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from .consumers import CHAT_TOPIC_GROUP, serialize_reply_for_ws

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            CHAT_TOPIC_GROUP.format(topic_id=topic_id),
            {
                'type': 'chat.reply.created',
                'reply': serialize_reply_for_ws(reply, is_pro_viewer=True),
            },
        )
    except Exception:
        # WS-broadcast — best-effort. Если упало (например, channel layer
        # ещё не сконфигурирован) — HTTP-ответ всё равно успешен.
        pass


def _broadcast_org_message(conv_id: int, msg: OrgConversationMessage):
    """Send message to org-conv-<id> WS group."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        from .consumers import ORG_CONV_GROUP, serialize_org_message_for_ws

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            ORG_CONV_GROUP.format(conv_id=conv_id),
            {
                'type': 'org.conv.message.created',
                'message': serialize_org_message_for_ws(msg),
            },
        )
    except Exception:
        pass


@login_required(login_url='accounts:login')
@require_POST
def chat_reaction_toggle(request):
    """Toggle реакции на топик или ответ. Free: только 👍. Pro: любой emoji."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'invalid_json'}, status=400)

    target_type = data.get('target_type')  # 'topic' | 'reply'
    target_id = data.get('target_id')
    emoji = (data.get('emoji') or '👍').strip()[:16]

    is_pro = _is_pro_or_enterprise(request.user)
    if not is_pro and emoji != '👍':
        return feature_denied_response(request.user, 'comments_rich', status=402)

    kwargs = {'user': request.user, 'emoji': emoji}
    if target_type == 'topic':
        try:
            topic = ChatTopic.objects.get(pk=int(target_id), moderation_status='visible')
        except (ChatTopic.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': 'topic_not_found'}, status=404)
        kwargs['target_topic'] = topic
    elif target_type == 'reply':
        try:
            reply = ChatReply.objects.get(pk=int(target_id), moderation_status='visible')
        except (ChatReply.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'ok': False, 'error': 'reply_not_found'}, status=404)
        kwargs['target_reply'] = reply
    else:
        return JsonResponse({'ok': False, 'error': 'bad_target_type'}, status=400)

    existing = ChatReaction.objects.filter(**kwargs).first()
    if existing:
        existing.delete()
        action = 'removed'
    else:
        ChatReaction.objects.create(**kwargs)
        action = 'added'

    return JsonResponse({'ok': True, 'action': action, 'emoji': emoji})


@login_required(login_url='accounts:login')
@require_POST
def chat_topic_pin_toggle(request, topic_id):
    """Pro-only: владелец может закрепить свой топик."""
    if not _is_pro_or_enterprise(request.user):
        return _form_error(
            request,
            'Закрепление топика — Pro-фича.',
            redirect_to='hello:chat_topic_detail',
            topic_id=topic_id,
            status=402,
        )
    topic = get_object_or_404(ChatTopic, pk=topic_id, author=request.user)
    topic.is_pinned = not topic.is_pinned
    topic.save(update_fields=['is_pinned'])
    return redirect('hello:chat_topic_detail', topic_id=topic_id)


@login_required(login_url='accounts:login')
@require_POST
def chat_reply_accept_answer(request, topic_id, reply_id):
    """Только автор топика может пометить ответ как accepted."""
    topic = get_object_or_404(ChatTopic, pk=topic_id, author=request.user, moderation_status='visible')
    reply = get_object_or_404(ChatReply, pk=reply_id, topic=topic, moderation_status='visible')
    # Снимаем предыдущий accepted (один на топик)
    ChatReply.objects.filter(topic=topic, is_accepted_answer=True).update(is_accepted_answer=False)
    reply.is_accepted_answer = True
    reply.save(update_fields=['is_accepted_answer'])
    topic.is_resolved = True
    topic.save(update_fields=['is_resolved'])
    return redirect('hello:chat_topic_detail', topic_id=topic_id)


def chat_topic_poll(request, topic_id):
    """AJAX-polling: возвращает reply'и с id > since_id. Используется
    клиентом каждые 8-10 секунд для авто-обновления тредов."""
    topic = get_object_or_404(ChatTopic, pk=topic_id, moderation_status='visible')
    since_id = 0
    try:
        since_id = int(request.GET.get('since_id') or 0)
    except (TypeError, ValueError):
        pass
    qs = visible_queryset(
        topic.replies.filter(id__gt=since_id).select_related('author', 'parent'),
        request.user,
    ).order_by('id')[:POLL_LIMIT]
    is_pro_viewer = _is_pro_or_enterprise(request.user) if request.user.is_authenticated else False
    return JsonResponse(
        {
            'ok': True,
            'replies': [_reply_to_dict(r, is_pro_viewer=is_pro_viewer) for r in qs],
            'topic': {'last_activity_at': topic.last_activity_at.isoformat()},
        }
    )


# ────────────────────────────────────────────────────────────────────────
# Org беседы (Enterprise)
# ────────────────────────────────────────────────────────────────────────


@login_required(login_url='accounts:login')
def org_conversation_list(request, org_slug):
    org = get_object_or_404(Organization, slug=org_slug)
    if not user_can(request.user, org, 'org.chat.read'):
        return HttpResponseForbidden('Нет доступа к беседам этой org.')
    conversations = list(
        org.conversations.select_related('created_by', 'attached_project')
        .filter(is_archived=False)
        .order_by('-last_activity_at')
    )
    archived = list(org.conversations.filter(is_archived=True).order_by('-last_activity_at')[:10])
    return render(
        request,
        'orgs/conversation_list.html',
        {
            'org': org,
            'conversations': conversations,
            'archived': archived,
            'can_create': user_can(request.user, org, 'org.chat.create_conversation'),
            'can_archive': user_can(request.user, org, 'org.chat.archive'),
        },
    )


@login_required(login_url='accounts:login')
@require_POST
def org_conversation_create(request, org_slug):
    org = get_object_or_404(Organization, slug=org_slug)
    if not user_can(request.user, org, 'org.chat.create_conversation'):
        return HttpResponseForbidden('Создание каналов — только для admin/owner.')

    title = (request.POST.get('title') or '').strip()[:200]
    description = (request.POST.get('description') or '').strip()
    if not title:
        return _form_error(
            request, 'Введите название канала.', redirect_to='hello:org_conversation_list', org_slug=org.slug
        )

    conv = OrgConversation.objects.create(
        organization=org,
        title=title,
        description=description,
        created_by=request.user,
    )
    # Audit-log: создание канала
    from .models import AuditLog

    AuditLog.log(
        actor=request.user,
        action='org.chat.conversation.create',
        organization=org,
        object_type='OrgConversation',
        object_id=conv.id,
        payload={'title': conv.title},
        request=request,
    )
    return redirect('hello:org_conversation_detail', org_slug=org.slug, conv_id=conv.id)


@login_required(login_url='accounts:login')
def org_conversation_detail(request, org_slug, conv_id):
    org = get_object_or_404(Organization, slug=org_slug)
    if not user_can(request.user, org, 'org.chat.read'):
        return HttpResponseForbidden('Нет доступа к беседам этой org.')
    conv = get_object_or_404(OrgConversation, pk=conv_id, organization=org)
    messages = list(
        visible_queryset(conv.messages.select_related('author', 'parent'), request.user).order_by(
            'created_at'
        )[:200]
    )
    # Все Enterprise = Pro, markdown по умолчанию
    rendered = [(m, _render_body(display_body(m, request.user), is_pro=True)) for m in messages]
    org_members = list(org.members.filter(deactivated_at__isnull=True).select_related('user'))
    return render(
        request,
        'orgs/conversation_detail.html',
        {
            'org': org,
            'conversation': conv,
            'rendered_messages': rendered,
            'can_post': user_can(request.user, org, 'org.chat.write'),
            'can_archive': user_can(request.user, org, 'org.chat.archive'),
            'org_members': org_members,
        },
    )


@login_required(login_url='accounts:login')
@require_POST
def org_conversation_message_create(request, org_slug, conv_id):
    org = get_object_or_404(Organization, slug=org_slug)
    if not user_can(request.user, org, 'org.chat.write'):
        return HttpResponseForbidden('Нет прав писать в беседы этой org.')
    if user_is_restricted(request.user, 'write', organization=org):
        return HttpResponseForbidden('Ваш аккаунт временно ограничен модератором.')
    conv = get_object_or_404(OrgConversation, pk=conv_id, organization=org, is_archived=False)

    body = (request.POST.get('body') or '').strip()
    if not body:
        return _form_error(
            request,
            'Пустое сообщение.',
            redirect_to='hello:org_conversation_detail',
            org_slug=org.slug,
            conv_id=conv.id,
        )

    parent = None
    parent_id = request.POST.get('parent_id')
    if parent_id:
        try:
            parent = OrgConversationMessage.objects.get(pk=int(parent_id), conversation=conv)
        except (OrgConversationMessage.DoesNotExist, ValueError, TypeError):
            parent = None

    # @mentions: парсим @username, оставляем только тех, кто реально member org
    mentions = _parse_mentions(body, org)

    msg = OrgConversationMessage.objects.create(
        conversation=conv,
        author=request.user,
        body=body,
        parent=parent,
        mentions=mentions,
    )
    OrgConversation.objects.filter(pk=conv.pk).update(last_activity_at=timezone.now())

    # Broadcast в WS-комнату канала
    _broadcast_org_message(conv.id, msg)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(
            {
                'ok': True,
                'message': {
                    'id': msg.id,
                    'author': request.user.username,
                    'body_html': _render_body(msg.body, is_pro=True),
                    'parent_id': parent.id if parent else None,
                    'created_at': msg.created_at.isoformat(),
                },
            }
        )
    return redirect('hello:org_conversation_detail', org_slug=org.slug, conv_id=conv.id)


@login_required(login_url='accounts:login')
@require_POST
def org_conversation_archive(request, org_slug, conv_id):
    org = get_object_or_404(Organization, slug=org_slug)
    if not user_can(request.user, org, 'org.chat.archive'):
        return HttpResponseForbidden('Архивирование — admin/owner.')
    conv = get_object_or_404(OrgConversation, pk=conv_id, organization=org)
    conv.is_archived = not conv.is_archived
    conv.save(update_fields=['is_archived'])
    from .models import AuditLog

    AuditLog.log(
        actor=request.user,
        action='org.chat.conversation.archive' if conv.is_archived else 'org.chat.conversation.unarchive',
        organization=org,
        object_type='OrgConversation',
        object_id=conv.id,
        request=request,
    )
    return redirect('hello:org_conversation_list', org_slug=org.slug)


@login_required(login_url='accounts:login')
def org_conversation_poll(request, org_slug, conv_id):
    org = get_object_or_404(Organization, slug=org_slug)
    if not user_can(request.user, org, 'org.chat.read'):
        return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)
    conv = get_object_or_404(OrgConversation, pk=conv_id, organization=org)
    since_id = 0
    try:
        since_id = int(request.GET.get('since_id') or 0)
    except (TypeError, ValueError):
        pass
    qs = visible_queryset(
        conv.messages.filter(id__gt=since_id).select_related('author', 'parent'),
        request.user,
    ).order_by('id')[:POLL_LIMIT]
    return JsonResponse(
        {
            'ok': True,
            'messages': [
                {
                    'id': m.id,
                    'author': m.author.username if m.author else 'удалённый',
                    'body_html': _render_body(display_body(m, request.user), is_pro=True),
                    'moderation_status': m.moderation_status,
                    'parent_id': m.parent_id,
                    'created_at': m.created_at.isoformat(),
                }
                for m in qs
            ],
        }
    )


# ────────────────────────────────────────────────────────────────────────
# Internal utils
# ────────────────────────────────────────────────────────────────────────


def _form_error(request, message, *, redirect_to, status=400, **kwargs):
    """Универсальный фронт: AJAX → JSON, иначе redirect с flash через GET-параметр."""
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': False, 'message': message}, status=status)
    url = reverse(redirect_to, kwargs=kwargs) if kwargs else reverse(redirect_to)
    # Для простоты сериализуем error в query, шаблон покажет
    from urllib.parse import quote

    return redirect(f'{url}?error={quote(message)}')


def _parse_mentions(body, org):
    """Извлекает @username из тела и оставляет только members org. Возвращает
    список user_id для удобной выборки notify-таргетов в будущем."""
    import re

    usernames = set(re.findall(r'@([A-Za-z0-9_.\-]{2,})', body or ''))
    if not usernames:
        return []
    from .models import OrganizationMember

    members = OrganizationMember.objects.filter(
        organization=org,
        deactivated_at__isnull=True,
        user__username__in=usernames,
    ).values_list('user_id', flat=True)
    return list(members)
