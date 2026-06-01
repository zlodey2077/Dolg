import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from Dolg_APP.models import (
    Comment,
    Organization,
    OrganizationMember,
    SchematicProject,
)
from Dolg_APP.org_permissions import user_can

from .models import ModerationAction, ModerationCase, ModerationReport, UserRestriction
from .permissions import (
    GROUP_SITE_MODERATOR,
    ensure_global_moderation_groups,
    user_can_moderate_site,
    user_can_moderate_target,
)
from .services import user_is_restricted


User = get_user_model()


class ModerationRoleTests(TestCase):
    def test_global_moderator_group_gets_moderation_permission(self):
        ensure_global_moderation_groups()
        moderator = User.objects.create_user('mod', 'mod@example.com', 'pw')
        support = User.objects.create_user('support', 'support@example.com', 'pw')
        moderator.groups.add(Group.objects.get(name=GROUP_SITE_MODERATOR))

        self.assertTrue(user_can_moderate_site(moderator))
        self.assertFalse(user_can_moderate_site(support))

    def test_org_moderator_can_moderate_only_own_organization(self):
        owner = User.objects.create_user('owner', 'owner@example.com', 'pw')
        moderator = User.objects.create_user('orgmod', 'orgmod@example.com', 'pw')
        outsider = User.objects.create_user('outsider', 'out@example.com', 'pw')
        org = Organization.objects.create(name='Team A', slug='team-a', billing_email='a@example.com', owner=owner)
        other_org = Organization.objects.create(name='Team B', slug='team-b', billing_email='b@example.com', owner=owner)
        OrganizationMember.objects.create(organization=org, user=moderator, role='moderator')
        project = SchematicProject.objects.create(user=owner, organization=org, visibility='team', name='Team project')
        other_project = SchematicProject.objects.create(user=owner, organization=other_org, visibility='team', name='Other project')

        self.assertTrue(user_can(moderator, org, 'org.moderation.manage'))
        self.assertTrue(user_can_moderate_target(moderator, project))
        self.assertFalse(user_can_moderate_target(moderator, other_project))
        self.assertFalse(user_can_moderate_target(outsider, project))


class ModerationApiTests(TestCase):
    def setUp(self):
        ensure_global_moderation_groups()
        self.author = User.objects.create_user('author', 'a@example.com', 'pw')
        self.reporter = User.objects.create_user('reporter', 'r@example.com', 'pw')
        self.moderator = User.objects.create_user('moderator', 'm@example.com', 'pw')
        self.moderator.groups.add(Group.objects.get(name=GROUP_SITE_MODERATOR))
        self.project = SchematicProject.objects.create(
            user=self.author,
            name='Moderated project',
            visibility='public',
        )
        self.comment = Comment.objects.create(user=self.author, project=self.project, body='Unsafe public text')
        self.client = Client()

    def test_report_creates_case_and_report(self):
        self.client.force_login(self.reporter)
        response = self.client.post(
            reverse('moderation:api_report'),
            data=json.dumps({
                'target_type': 'comment',
                'target_id': self.comment.id,
                'reason': 'abuse',
                'details': 'bad wording',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(ModerationCase.objects.count(), 1)
        self.assertEqual(ModerationReport.objects.count(), 1)
        self.assertEqual(data['report']['case_id'], ModerationCase.objects.first().id)

    def test_moderator_hides_comment_and_public_list_excludes_it(self):
        self.client.force_login(self.reporter)
        report_response = self.client.post(
            reverse('moderation:api_report'),
            data=json.dumps({'target_type': 'comment', 'target_id': self.comment.id, 'reason': 'spam'}),
            content_type='application/json',
        )
        case_id = report_response.json()['case']['id']

        self.client.force_login(self.moderator)
        action_response = self.client.post(
            reverse('moderation:api_case_action', args=[case_id]),
            data=json.dumps({'action': 'hide', 'reason': 'contains spam'}),
            content_type='application/json',
        )

        self.assertEqual(action_response.status_code, 200)
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.moderation_status, 'hidden')
        self.assertEqual(ModerationAction.objects.filter(action_type='hide').count(), 1)

        anonymous = Client()
        list_response = anonymous.get(reverse('hello:api_comments_list'), {'project': self.project.id})
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()['comments'], [])

        self.client.force_login(self.author)
        author_response = self.client.get(reverse('hello:api_comments_list'), {'project': self.project.id})
        self.assertEqual(len(author_response.json()['comments']), 1)
        self.assertIn('Скрыто', author_response.json()['comments'][0]['body'])

    def test_user_restriction_blocks_chat_writes(self):
        UserRestriction.objects.create(
            user=self.author,
            restriction_type='mute',
            scope='global',
            reason='flood',
            expires_at=timezone.now() + timedelta(days=1),
            created_by=self.moderator,
        )
        self.assertTrue(user_is_restricted(self.author, 'write'))
        self.client.force_login(self.author)

        response = self.client.post(
            reverse('hello:chat_topic_create'),
            data={'title': 'Blocked topic', 'body': 'Cannot post'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['ok'])
