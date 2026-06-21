"""Тесты Enterprise tier.

Покрывают:
- Organization / OrganizationMember / OrganizationInvite модели
- Role-based permissions (owner > admin > engineer > reviewer > viewer)
- Audit-log (создание, запись, фильтры)
- Team-projects (visibility, доступ)
- Approval workflow (submit / approve / reject)
- Centralized billing (org-subscription дает pro всем members)
- Mock SSO endpoint
- API tokens (create / revoke)
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from Dolg_APP.models import (
    AuditLog,
    Organization,
    OrganizationApiToken,
    OrganizationInvite,
    OrganizationMember,
    SchematicProject,
    Subscription,
)
from Dolg_APP.org_permissions import user_can
from Dolg_APP.quotas import get_user_tier

User = get_user_model()


def _make_user(username, verified=True):
    user = User.objects.create_user(username=username, email=f'{username}@x.test', password='Pass-123456')
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if verified:
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])
    return user


def _make_org_with_owner(slug='acme', owner=None):
    if owner is None:
        owner = _make_user('owner_' + slug)
    org = Organization.objects.create(
        name=slug.title(),
        slug=slug,
        billing_email='b@x.test',
        owner=owner,
    )
    OrganizationMember.objects.create(organization=org, user=owner, role='owner')
    return org, owner


def _activate_enterprise_org(org):
    org.plan = 'enterprise'
    org.seats_max = max(org.seats_max, 100)
    org.save(update_fields=['plan', 'seats_max'])
    Subscription.objects.create(
        organization=org,
        tier='pro',
        status='active',
        period_end=timezone.now() + timedelta(days=30),
    )
    return org


# ============================================================
# Models
# ============================================================
class OrganizationModelTests(TestCase):
    def test_create_and_membership(self):
        org, owner = _make_org_with_owner()
        self.assertEqual(org.active_members_count(), 1)
        self.assertTrue(org.has_member(owner))
        self.assertEqual(org.get_role(owner), 'owner')

    def test_invite_lifecycle(self):
        org, owner = _make_org_with_owner('acme2')
        invite = OrganizationInvite.objects.create(
            organization=org,
            email='new@x.test',
            token='abc123',
            role='engineer',
            invited_by=owner,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(invite.is_pending())
        self.assertFalse(invite.is_expired())

        # Expired
        invite.expires_at = timezone.now() - timedelta(days=1)
        invite.save()
        self.assertTrue(invite.is_expired())

    def test_deactivated_member_not_counted(self):
        org, owner = _make_org_with_owner('acme3')
        eng = _make_user('eng_3')
        m = OrganizationMember.objects.create(organization=org, user=eng, role='engineer')
        self.assertEqual(org.active_members_count(), 2)
        m.deactivated_at = timezone.now()
        m.save(update_fields=['deactivated_at'])
        self.assertEqual(org.active_members_count(), 1)
        self.assertFalse(org.has_member(eng))


# ============================================================
# Permissions
# ============================================================
class PermissionsTests(TestCase):
    def setUp(self):
        self.org, self.owner = _make_org_with_owner('p-org')
        self.admin = _make_user('admin_u')
        self.engineer = _make_user('eng_u')
        self.reviewer = _make_user('rev_u')
        self.viewer = _make_user('view_u')
        self.outsider = _make_user('outsider')
        for u, r in [
            (self.admin, 'admin'),
            (self.engineer, 'engineer'),
            (self.reviewer, 'reviewer'),
            (self.viewer, 'viewer'),
        ]:
            OrganizationMember.objects.create(organization=self.org, user=u, role=r)

    def test_owner_can_everything(self):
        for action in ['org.delete', 'org.billing', 'bom.approve', 'project.delete']:
            self.assertTrue(user_can(self.owner, self.org, action), f'owner missing {action}')

    def test_admin_can_manage_users_but_not_billing(self):
        self.assertTrue(user_can(self.admin, self.org, 'org.members.invite'))
        self.assertFalse(user_can(self.admin, self.org, 'org.billing'))
        self.assertFalse(user_can(self.admin, self.org, 'org.delete'))

    def test_engineer_can_edit_team_project_not_approve(self):
        self.assertTrue(user_can(self.engineer, self.org, 'project.edit_team'))
        self.assertFalse(user_can(self.engineer, self.org, 'bom.approve'))

    def test_reviewer_can_approve_not_edit(self):
        self.assertTrue(user_can(self.reviewer, self.org, 'bom.approve'))
        self.assertFalse(user_can(self.reviewer, self.org, 'project.edit_team'))

    def test_viewer_read_only(self):
        self.assertTrue(user_can(self.viewer, self.org, 'project.read'))
        self.assertFalse(user_can(self.viewer, self.org, 'bom.submit'))

    def test_outsider_has_no_permissions(self):
        for action in ['project.read', 'project.edit_team', 'bom.approve']:
            self.assertFalse(user_can(self.outsider, self.org, action))


# ============================================================
# Audit log
# ============================================================
class AuditLogTests(TestCase):
    def test_log_creates_entry(self):
        org, owner = _make_org_with_owner('a-log')
        entry = AuditLog.log(
            actor=owner,
            action='test.action',
            organization=org,
            object_type='Test',
            object_id=42,
            payload={'k': 'v'},
        )
        self.assertEqual(entry.actor, owner)
        self.assertEqual(entry.action, 'test.action')
        self.assertEqual(entry.payload, {'k': 'v'})

    def test_log_filters_by_action_and_actor(self):
        org, owner = _make_org_with_owner('a-log2')
        for action in ['a.x', 'a.y', 'b.x']:
            AuditLog.log(actor=owner, action=action, organization=org)
        a_count = org.audit_log.filter(action__startswith='a.').count()
        self.assertEqual(a_count, 2)


# ============================================================
# Team projects + visibility
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class TeamProjectsTests(TestCase):
    def setUp(self):
        self.org, self.owner = _make_org_with_owner('t-proj')
        self.engineer = _make_user('t_eng')
        self.outsider = _make_user('t_out')
        OrganizationMember.objects.create(organization=self.org, user=self.engineer, role='engineer')

    def test_team_project_creation_via_api(self):
        self.client.force_login(self.engineer)
        import json as _j

        r = self.client.post(
            reverse('hello:api_project_create'),
            data=_j.dumps({'name': 'team-proj', 'organization_slug': 't-proj'}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200, r.content)
        p_data = r.json()['project']
        self.assertEqual(p_data['organization'], 't-proj')
        self.assertEqual(p_data['visibility'], 'team')

    def test_outsider_cannot_create_team_project(self):
        self.client.force_login(self.outsider)
        import json as _j

        r = self.client.post(
            reverse('hello:api_project_create'),
            data=_j.dumps({'name': 'x', 'organization_slug': 't-proj'}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 403)


# ============================================================
# Approval workflow
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class ApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.org, self.owner = _make_org_with_owner('apw')
        _activate_enterprise_org(self.org)
        self.engineer = _make_user('apw_eng')
        self.reviewer = _make_user('apw_rev')
        OrganizationMember.objects.create(organization=self.org, user=self.engineer, role='engineer')
        OrganizationMember.objects.create(organization=self.org, user=self.reviewer, role='reviewer')
        self.project = SchematicProject.objects.create(
            user=self.engineer,
            organization=self.org,
            visibility='team',
            name='for-approval',
        )

    def test_engineer_submits_for_review(self):
        self.client.force_login(self.engineer)
        r = self.client.post(
            reverse('hello:project_submit_for_review', kwargs={'org_slug': 'apw', 'pk': self.project.id})
        )
        self.assertEqual(r.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.approval_state, 'pending_review')

    def test_reviewer_approves(self):
        self.project.approval_state = 'pending_review'
        self.project.save(update_fields=['approval_state'])
        self.client.force_login(self.reviewer)
        r = self.client.post(
            reverse('hello:project_approve', kwargs={'org_slug': 'apw', 'pk': self.project.id}),
            {'comment': 'looks good'},
        )
        self.assertEqual(r.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.approval_state, 'approved')
        # Audit fixed
        self.assertTrue(self.org.audit_log.filter(action='bom.approve').exists())

    def test_engineer_cannot_approve(self):
        self.project.approval_state = 'pending_review'
        self.project.save(update_fields=['approval_state'])
        self.client.force_login(self.engineer)
        r = self.client.post(
            reverse('hello:project_approve', kwargs={'org_slug': 'apw', 'pk': self.project.id})
        )
        self.assertEqual(r.status_code, 403)


# ============================================================
# Centralized billing
# ============================================================
class CentralizedBillingTests(TestCase):
    def test_org_subscription_grants_pro_to_all_members(self):
        org, owner = _make_org_with_owner('biz')
        eng = _make_user('biz_eng')
        OrganizationMember.objects.create(organization=org, user=eng, role='engineer')

        # Подписка на org
        Subscription.objects.create(
            organization=org,
            tier='pro',
            status='active',
            period_end=timezone.now() + timedelta(days=30),
        )

        # Engineer без личной Pro — но получает pro tier через org
        self.assertEqual(get_user_tier(eng), 'pro')

    def test_no_org_sub_means_free(self):
        org, owner = _make_org_with_owner('biz2')
        eng = _make_user('biz2_eng')
        OrganizationMember.objects.create(organization=org, user=eng, role='engineer')
        self.assertEqual(get_user_tier(eng), 'free')


# ============================================================
# Org views (HTTP)
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class OrgPagesTests(TestCase):
    def test_org_list_auth_required(self):
        r = self.client.get('/orgs/')
        self.assertEqual(r.status_code, 302)

    def test_org_create_form_renders(self):
        user = _make_user('view_user')
        self.client.force_login(user)
        r = self.client.get('/orgs/create/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Создать команду')

    def test_org_create_via_post(self):
        user = _make_user('cu')
        self.client.force_login(user)
        r = self.client.post(
            '/orgs/create/',
            {
                'name': 'New Org',
                'slug': 'new-org',
                'billing_email': 'b@x.test',
                'expected_size': '1-5',
                'agree_msa': 'on',
                'agree_dpa': 'on',
                'agree_aup': 'on',
                'agree_privacy': 'on',
            },
        )
        self.assertEqual(r.status_code, 302)
        org = Organization.objects.get(slug='new-org')
        self.assertEqual(org.owner, user)
        # Audit логирует
        self.assertTrue(org.audit_log.filter(action='org.create').exists())

    def test_member_cannot_access_other_org(self):
        org, owner = _make_org_with_owner('locked')
        outsider = _make_user('out_user')
        self.client.force_login(outsider)
        r = self.client.get('/orgs/locked/')
        self.assertEqual(r.status_code, 403)


# ============================================================
# Invite-flow
# ============================================================
@override_settings(
    ALLOWED_HOSTS=['*'],
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class InviteFlowTests(TestCase):
    def test_invite_creates_record_and_sends_email(self):
        from django.core import mail

        org, owner = _make_org_with_owner('inv-org')
        self.client.force_login(owner)
        r = self.client.post('/orgs/inv-org/members/invite/', {'email': 'newone@x.test', 'role': 'engineer'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(org.invites.filter(email='newone@x.test').exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('inv-org', mail.outbox[0].body)

    def test_accept_invite_creates_member(self):
        org, owner = _make_org_with_owner('inv-org2')
        invitee = _make_user('invitee')
        invite = OrganizationInvite.objects.create(
            organization=org,
            email=invitee.email,
            token='tok123',
            role='engineer',
            expires_at=timezone.now() + timedelta(days=7),
            invited_by=owner,
        )
        self.client.force_login(invitee)
        r = self.client.get('/orgs/inv-org2/invite/tok123/')
        self.assertEqual(r.status_code, 302)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)
        self.assertTrue(org.has_member(invitee))


# ============================================================
# API tokens
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class ApiTokenTests(TestCase):
    def test_create_and_revoke_token(self):
        org, owner = _make_org_with_owner('tok-org')
        _activate_enterprise_org(org)
        self.client.force_login(owner)
        r = self.client.post('/orgs/tok-org/api-tokens/create/', {'name': 'CI', 'scope': 'projects.read'})
        self.assertEqual(r.status_code, 302)
        raw_token = self.client.session.get('_just_created_token')
        self.assertTrue(raw_token.startswith(OrganizationApiToken.TOKEN_PREFIX))

        tok = OrganizationApiToken.objects.get(organization=org)
        self.assertNotEqual(tok.token, raw_token)
        self.assertTrue(OrganizationApiToken.is_hashed_token(tok.token))
        self.assertTrue(tok.matches(raw_token))
        self.assertFalse(tok.matches(raw_token + 'x'))
        self.assertTrue(tok.is_active())

        r2 = self.client.post(f'/orgs/tok-org/api-tokens/{tok.id}/revoke/')
        self.assertEqual(r2.status_code, 302)
        tok.refresh_from_db()
        self.assertFalse(tok.is_active())

    def test_invalid_token_scope_is_rejected(self):
        org, owner = _make_org_with_owner('tok-scope')
        _activate_enterprise_org(org)
        self.client.force_login(owner)

        r = self.client.post(
            '/orgs/tok-scope/api-tokens/create/', {'name': 'Bad', 'scope': 'projects.read,admin.all'}
        )

        self.assertEqual(r.status_code, 302)
        self.assertFalse(OrganizationApiToken.objects.filter(organization=org).exists())
        self.assertIsNone(self.client.session.get('_just_created_token'))

    @override_settings(ORG_API_TOKEN_ACTIVE_LIMIT=2)
    def test_active_token_limit_is_enforced(self):
        org, owner = _make_org_with_owner('tok-limit')
        _activate_enterprise_org(org)
        self.client.force_login(owner)

        for idx in range(2):
            raw_token = OrganizationApiToken.make_raw_token()
            OrganizationApiToken.objects.create(
                organization=org,
                name=f'CI {idx}',
                token=OrganizationApiToken.hash_token(raw_token),
                scope=['projects.read'],
                created_by=owner,
            )

        r = self.client.post(
            '/orgs/tok-limit/api-tokens/create/', {'name': 'Overflow', 'scope': 'projects.read'}
        )

        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            OrganizationApiToken.objects.filter(organization=org, revoked_at__isnull=True).count(), 2
        )
        self.assertIsNone(self.client.session.get('_just_created_token'))


# ============================================================
# SSO
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class MockSsoTests(TestCase):
    def setUp(self):
        self.org, self.owner = _make_org_with_owner('sso-org')
        self.org.settings = {'sso_enabled': True, 'sso_provider': 'azure'}
        self.org.save()

    def test_sso_redirect_renders(self):
        r = self.client.get('/sso/sso-org/redirect/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Azure')

    def test_sso_callback_creates_user_and_member(self):
        # Сначала redirect — устанавливает nonce
        self.client.get('/sso/sso-org/redirect/')
        nonce = self.client.session.get('sso_nonce')
        self.assertIsNotNone(nonce)
        # Callback с тем же nonce
        r = self.client.post(
            '/sso/sso-org/callback/',
            {
                'email': 'sso-user@acme.com',
                'nonce': nonce,
            },
        )
        self.assertEqual(r.status_code, 302)
        # User создан, в org
        new_user = User.objects.get(email='sso-user@acme.com')
        self.assertTrue(self.org.has_member(new_user))
        # Audit логирует
        self.assertTrue(self.org.audit_log.filter(action='auth.sso_login').exists())

    def test_sso_disabled_redirects_to_login(self):
        self.org.settings = {'sso_enabled': False}
        self.org.save()
        r = self.client.get('/sso/sso-org/redirect/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r.url)
