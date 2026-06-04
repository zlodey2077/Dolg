"""Тесты системы чатов и бесед.

Покрывают:
- ChatTopic / ChatReply / ChatReaction CRUD
- Permissions: guest read-only, Free пишет, Pro = pin + custom emoji
- Rate limits Free: 5 топиков, 20 reply в день
- OrgConversation: только members org, admin создаёт
- Announcement: показывается в сайдбаре, expires
- Polling endpoints
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from Dolg_APP.billing import activate_pro
from Dolg_APP.models import (
    Announcement,
    ChatReaction,
    ChatReply,
    ChatTopic,
    DailyUsage,
    Organization,
    OrganizationMember,
    OrgConversation,
)

User = get_user_model()


def _make_user(username, verified=True):
    user = User.objects.create_user(username=username, email=f'{username}@x.test', password='Pass-123456')
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if verified:
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])
    return user


def _make_org_with_owner(slug='c-org', owner=None):
    if owner is None:
        owner = _make_user('owner_' + slug.replace('-', '_'))
    org = Organization.objects.create(
        name=slug.title(),
        slug=slug,
        billing_email='b@x.test',
        owner=owner,
    )
    OrganizationMember.objects.create(organization=org, user=owner, role='owner')
    return org, owner


# ============================================================
# ChatTopic / ChatReply models
# ============================================================
class ChatModelTests(TestCase):
    def test_topic_create_and_str(self):
        u = _make_user('mt_u')
        t = ChatTopic.objects.create(title='How to use ngspice?', body='?', author=u)
        self.assertEqual(t.reply_count(), 0)
        self.assertIn('ngspice', str(t))

    def test_reply_threading(self):
        u = _make_user('mt_r')
        t = ChatTopic.objects.create(title='T', body='b', author=u)
        r1 = ChatReply.objects.create(topic=t, author=u, body='answer 1')
        r2 = ChatReply.objects.create(topic=t, author=u, body='nested', parent=r1)
        self.assertEqual(r2.parent_id, r1.id)
        self.assertEqual(t.reply_count(), 2)

    def test_reaction_unique_per_user_emoji(self):
        u = _make_user('mt_react')
        t = ChatTopic.objects.create(title='T', body='b', author=u)
        ChatReaction.objects.create(target_topic=t, user=u, emoji='👍')
        with self.assertRaises(Exception):
            ChatReaction.objects.create(target_topic=t, user=u, emoji='👍')


# ============================================================
# Permissions and tier-gated features
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class ChatPermissionsTests(TestCase):
    def setUp(self):
        self.free_user = _make_user('free_u')
        self.pro_user = _make_user('pro_u')
        activate_pro(self.pro_user, months=1, provider='manual')
        self.topic = ChatTopic.objects.create(title='Demo', body='b', author=self.free_user)

    def test_guest_can_read_list_and_detail(self):
        # Не login
        r = self.client.get(reverse('hello:chat_list'))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse('hello:chat_topic_detail', args=[self.topic.id]))
        self.assertEqual(r.status_code, 200)
        # Не должно быть формы reply
        self.assertNotIn(b'name="body"', r.content.split(b'<form')[1] if b'<form' in r.content else b'')

    def test_guest_cannot_post(self):
        r = self.client.post(
            reverse('hello:chat_topic_create'), {'title': 't', 'body': 'b', 'category': 'general'}
        )
        # @login_required → redirect to login
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.url.lower())

    def test_free_user_can_create_topic(self):
        self.client.force_login(self.free_user)
        r = self.client.post(
            reverse('hello:chat_topic_create'),
            {'title': 'My question', 'body': 'help me', 'category': 'simulation'},
        )
        self.assertEqual(r.status_code, 302)
        t = ChatTopic.objects.get(title='My question')
        self.assertEqual(t.author, self.free_user)

    def test_free_user_cannot_pin_topic(self):
        self.client.force_login(self.free_user)
        r = self.client.post(reverse('hello:chat_topic_pin_toggle', args=[self.topic.id]))
        # Free → 302 redirect с error (status 402 ниже не нужен здесь)
        self.assertEqual(r.status_code, 302)
        self.topic.refresh_from_db()
        self.assertFalse(self.topic.is_pinned)

    def test_pro_user_can_pin_own_topic(self):
        pro_topic = ChatTopic.objects.create(title='Pro T', body='b', author=self.pro_user)
        self.client.force_login(self.pro_user)
        r = self.client.post(reverse('hello:chat_topic_pin_toggle', args=[pro_topic.id]))
        self.assertEqual(r.status_code, 302)
        pro_topic.refresh_from_db()
        self.assertTrue(pro_topic.is_pinned)

    def test_free_user_emoji_restricted_to_thumbs(self):
        self.client.force_login(self.free_user)
        import json as _j

        r = self.client.post(
            reverse('hello:chat_reaction_toggle'),
            data=_j.dumps({'target_type': 'topic', 'target_id': self.topic.id, 'emoji': '🎉'}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 402)
        self.assertFalse(ChatReaction.objects.filter(target_topic=self.topic, emoji='🎉').exists())

    def test_pro_user_can_use_custom_emoji(self):
        self.client.force_login(self.pro_user)
        import json as _j

        r = self.client.post(
            reverse('hello:chat_reaction_toggle'),
            data=_j.dumps({'target_type': 'topic', 'target_id': self.topic.id, 'emoji': '🚀'}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            ChatReaction.objects.filter(target_topic=self.topic, emoji='🚀', user=self.pro_user).exists()
        )


# ============================================================
# Rate limits Free (5 топиков/день, 20 reply/день)
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class ChatRateLimitTests(TestCase):
    def setUp(self):
        self.user = _make_user('rl_u')
        self.client.force_login(self.user)

    def test_free_topic_quota_hit(self):
        # Симулируем 5 уже созданных топиков сегодня
        usage = DailyUsage.get_today(self.user)
        usage.chat_topics_count = 5
        usage.save(update_fields=['chat_topics_count'])

        self.client.post(
            reverse('hello:chat_topic_create'),
            {
                'title': 't',
                'body': 'b',
                'category': 'general',
            },
        )
        # Должен быть redirect с error (или 400 для AJAX). Топик НЕ создан.
        self.assertEqual(ChatTopic.objects.filter(author=self.user).count(), 0)

    def test_free_reply_quota_hit(self):
        topic = ChatTopic.objects.create(title='T', body='b', author=self.user)
        usage = DailyUsage.get_today(self.user)
        usage.chat_replies_count = 20
        usage.save(update_fields=['chat_replies_count'])

        self.client.post(reverse('hello:chat_reply_create', args=[topic.id]), {'body': 'r'})
        self.assertEqual(ChatReply.objects.filter(topic=topic).count(), 0)


# ============================================================
# Polling endpoints
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class ChatPollingTests(TestCase):
    def test_topic_poll_returns_only_new_replies(self):
        u = _make_user('poll_u')
        topic = ChatTopic.objects.create(title='Poll T', body='b', author=u)
        r1 = ChatReply.objects.create(topic=topic, author=u, body='r1')
        r2 = ChatReply.objects.create(topic=topic, author=u, body='r2')

        # Без since_id → оба
        r = self.client.get(reverse('hello:chat_topic_poll', args=[topic.id]))
        data = r.json()
        self.assertEqual(len(data['replies']), 2)

        # since_id=r1.id → только r2
        r = self.client.get(reverse('hello:chat_topic_poll', args=[topic.id]) + f'?since_id={r1.id}')
        data = r.json()
        self.assertEqual(len(data['replies']), 1)
        self.assertEqual(data['replies'][0]['id'], r2.id)


# ============================================================
# Org conversations (Enterprise)
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class OrgConversationTests(TestCase):
    def setUp(self):
        self.org, self.owner = _make_org_with_owner('conv-org')
        self.engineer = _make_user('cv_eng')
        self.outsider = _make_user('cv_out')
        OrganizationMember.objects.create(organization=self.org, user=self.engineer, role='engineer')

    def test_only_admin_can_create_conversation(self):
        # Engineer → 403
        self.client.force_login(self.engineer)
        r = self.client.post(
            reverse('hello:org_conversation_create', args=[self.org.slug]),
            {
                'title': 'Sprint planning',
                'description': '',
            },
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.org.conversations.count(), 0)

        # Owner → ok
        self.client.force_login(self.owner)
        r = self.client.post(
            reverse('hello:org_conversation_create', args=[self.org.slug]),
            {
                'title': 'Sprint planning',
                'description': '',
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.org.conversations.count(), 1)

    def test_outsider_blocked_from_list_and_detail(self):
        conv = OrgConversation.objects.create(organization=self.org, title='Private', created_by=self.owner)
        self.client.force_login(self.outsider)
        r = self.client.get(reverse('hello:org_conversation_list', args=[self.org.slug]))
        self.assertEqual(r.status_code, 403)
        r = self.client.get(reverse('hello:org_conversation_detail', args=[self.org.slug, conv.id]))
        self.assertEqual(r.status_code, 403)

    def test_engineer_can_post_message(self):
        conv = OrgConversation.objects.create(organization=self.org, title='Sprint', created_by=self.owner)
        self.client.force_login(self.engineer)
        r = self.client.post(
            reverse('hello:org_conversation_message_create', args=[self.org.slug, conv.id]),
            {'body': 'Hello team **bold**'},
        )
        self.assertEqual(r.status_code, 302)
        msgs = list(conv.messages.all())
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].author, self.engineer)

    def test_archived_conversation_rejects_new_messages(self):
        conv = OrgConversation.objects.create(
            organization=self.org,
            title='Old',
            created_by=self.owner,
            is_archived=True,
        )
        self.client.force_login(self.engineer)
        r = self.client.post(
            reverse('hello:org_conversation_message_create', args=[self.org.slug, conv.id]), {'body': 'no'}
        )
        # 404 because filter() excludes is_archived=True in view get_object_or_404
        self.assertEqual(r.status_code, 404)
        self.assertEqual(conv.messages.count(), 0)

    def test_admin_can_archive(self):
        conv = OrgConversation.objects.create(organization=self.org, title='Sprint', created_by=self.owner)
        self.client.force_login(self.owner)
        r = self.client.post(reverse('hello:org_conversation_archive', args=[self.org.slug, conv.id]))
        self.assertEqual(r.status_code, 302)
        conv.refresh_from_db()
        self.assertTrue(conv.is_archived)

    def test_mentions_parsed(self):
        conv = OrgConversation.objects.create(organization=self.org, title='M', created_by=self.owner)
        self.client.force_login(self.engineer)
        r = self.client.post(
            reverse('hello:org_conversation_message_create', args=[self.org.slug, conv.id]),
            {'body': f'Hi @{self.owner.username} please review'},
        )
        self.assertEqual(r.status_code, 302)
        msg = conv.messages.first()
        self.assertIn(self.owner.id, msg.mentions)


# ============================================================
# Announcement: sidebar visibility
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class AnnouncementTests(TestCase):
    def test_published_active_announcement_visible_in_sidebar(self):
        Announcement.objects.create(title='Release v2.5', body='New features', level='info')
        r = self.client.get(reverse('hello:chat_list'))
        self.assertContains(r, 'Release v2.5')

    def test_unpublished_not_in_sidebar(self):
        Announcement.objects.create(title='Draft news', body='b', is_published=False)
        r = self.client.get(reverse('hello:chat_list'))
        self.assertNotContains(r, 'Draft news')

    def test_expired_announcement_not_in_sidebar(self):
        Announcement.objects.create(
            title='Old news',
            body='b',
            expires_at=timezone.now() - timedelta(days=1),
        )
        r = self.client.get(reverse('hello:chat_list'))
        self.assertNotContains(r, 'Old news')
