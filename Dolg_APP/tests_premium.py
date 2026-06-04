"""Тесты Premium / Pro tier.

Покрывают:
- Subscription модель + helpers (trial / activate / cancel / expire)
- Tier-detection через get_user_tier
- AI pipeline: 4 метода + Pro-only защита
- Comments: Free plain / Pro Markdown + XSS-sanitize
- Custom logo upload (Pro-only)
- CAD-темы UI флаг
- Pro-badge в navbar
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import UserProfile
from Dolg_APP.billing import activate_pro, activate_trial, cancel, get_or_create_subscription
from Dolg_APP.models import Comment, Organization, OrganizationMember, SchematicProject, Subscription
from Dolg_APP.quotas import get_user_tier
from Dolg_APP.services.entitlements import get_effective_plan, has_feature

User = get_user_model()


def _make_user(username='alice', verified=True):
    user = User.objects.create_user(username=username, email=f'{username}@x.test', password='Strong-pass-123')
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if verified:
        profile.email_verified = True
        profile.save(update_fields=['email_verified'])
    return user


# ============================================================
# Subscription / billing helpers
# ============================================================
class SubscriptionTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_get_or_create_creates_free(self):
        sub = get_or_create_subscription(self.user)
        self.assertEqual(sub.tier, 'free')
        self.assertEqual(sub.status, 'active')

    def test_activate_trial_makes_pro_for_14_days(self):
        ok, msg = activate_trial(self.user)
        self.assertTrue(ok)
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.tier, 'pro')
        self.assertEqual(sub.status, 'trial')
        self.assertTrue(sub.trial_used)
        # period_end ≈ now + 14 days
        delta = sub.period_end - timezone.now()
        self.assertGreater(delta.days, 12)
        self.assertLess(delta.days, 15)

    def test_trial_only_once(self):
        activate_trial(self.user)
        ok, msg = activate_trial(self.user)
        self.assertFalse(ok)
        self.assertIn('уже', msg.lower())

    def test_activate_pro_extends_period(self):
        activate_pro(self.user, months=1)
        sub = Subscription.objects.get(user=self.user)
        first_end = sub.period_end
        # Активируем ещё месяц — должно продлить, а не reset
        activate_pro(self.user, months=2)
        sub.refresh_from_db()
        self.assertGreater(sub.period_end, first_end)

    def test_cancel_sets_status_cancelled(self):
        activate_pro(self.user, months=1)
        ok, _ = cancel(self.user)
        self.assertTrue(ok)
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.status, 'cancelled')
        self.assertFalse(sub.auto_renew)
        # is_pro_active всё ещё true (доступ до period_end)
        self.assertTrue(sub.is_pro_active())

    def test_get_user_tier_pro(self):
        activate_trial(self.user)
        self.assertEqual(get_user_tier(self.user), 'pro')

    def test_get_user_tier_free_default(self):
        self.assertEqual(get_user_tier(self.user), 'free')

    def test_entitlements_distinguish_free_pro_enterprise_and_staff(self):
        free = _make_user('ent_free')
        pro = _make_user('ent_pro')
        enterprise_user = _make_user('ent_enterprise')
        staff = _make_user('ent_staff')
        staff.is_staff = True
        staff.save(update_fields=['is_staff'])

        activate_trial(pro)
        org_owner = _make_user('ent_owner')
        org = Organization.objects.create(
            name='Ent Org',
            slug='ent-org',
            billing_email='billing@x.test',
            owner=org_owner,
            plan='enterprise',
            seats_max=100,
        )
        OrganizationMember.objects.create(organization=org, user=org_owner, role='owner')
        OrganizationMember.objects.create(organization=org, user=enterprise_user, role='engineer')
        Subscription.objects.create(
            organization=org,
            tier='pro',
            status='active',
            period_end=timezone.now() + timedelta(days=30),
        )

        self.assertEqual(get_effective_plan(free), 'free')
        self.assertEqual(get_effective_plan(pro), 'pro')
        self.assertEqual(get_effective_plan(enterprise_user, organization=org), 'enterprise')
        self.assertEqual(get_effective_plan(staff), 'unlimited')
        self.assertFalse(has_feature(free, 'pro_fft'))
        self.assertTrue(has_feature(pro, 'pro_fft'))
        self.assertTrue(has_feature(enterprise_user, 'enterprise_team_ai_memory', organization=org))

    def test_expire_command_degrades_pro(self):
        activate_pro(self.user, months=1)
        sub = Subscription.objects.get(user=self.user)
        sub.period_end = timezone.now() - timedelta(days=1)
        sub.status = 'cancelled'  # auto_renew по умолчанию True после activate_pro
        sub.save()
        call_command('expire_subscriptions')
        sub.refresh_from_db()
        self.assertEqual(sub.tier, 'free')
        self.assertEqual(sub.status, 'expired')


# ============================================================
# Billing страница
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class BillingPageTests(TestCase):
    def test_billing_page_accessible_for_guest(self):
        r = self.client.get('/billing/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Free')
        self.assertContains(r, 'Pro')

    def test_trial_button_visible_for_free_user(self):
        user = _make_user()
        self.client.force_login(user)
        r = self.client.get('/billing/')
        self.assertContains(r, 'trial')

    def test_activate_trial_endpoint(self):
        user = _make_user()
        self.client.force_login(user)
        r = self.client.post('/billing/trial/')
        self.assertEqual(r.status_code, 302)
        sub = Subscription.objects.get(user=user)
        self.assertEqual(sub.tier, 'pro')


# ============================================================
# AI Pipeline
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class AIPipelineTests(TestCase):
    def setUp(self):
        self.free = _make_user('free_user')
        self.pro = _make_user('pro_user')
        activate_trial(self.pro)
        self.demo_scheme = {
            'components': [
                {'id': 1, 'type': 'battery', 'x': 0, 'y': 0, 'label': 'V1'},
                {'id': 2, 'type': 'resistor', 'x': 100, 'y': 0, 'label': 'R1'},
                {'id': 3, 'type': 'capacitor', 'x': 200, 'y': 50, 'label': 'C1'},
                {'id': 4, 'type': 'ground', 'x': 200, 'y': 200},
            ],
            'connections': [
                {'from': {'compId': 1, 'portId': '+'}, 'to': {'compId': 2, 'portId': 'a'}},
                {'from': {'compId': 2, 'portId': 'b'}, 'to': {'compId': 3, 'portId': 'a'}},
                {'from': {'compId': 3, 'portId': 'b'}, 'to': {'compId': 4, 'portId': 'a'}},
            ],
        }

    def test_pipeline_info_public(self):
        r = self.client.get('/api/ai/pipeline/info/')
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['backend'], 'heuristic')
        self.assertIn('find_analogs', data['capabilities'])

    def test_anomalies_endpoint_free_allowed(self):
        self.client.force_login(self.free)
        import json as _j

        r = self.client.post(
            '/api/ai/pipeline/anomalies/',
            data=_j.dumps({'scheme_data': self.demo_scheme}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['action'], 'detect_anomalies')

    def test_explain_endpoint_blocked_for_free(self):
        self.client.force_login(self.free)
        import json as _j

        r = self.client.post(
            '/api/ai/pipeline/explain/',
            data=_j.dumps({'scheme_data': self.demo_scheme}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get('error'), 'plan_required')
        self.assertEqual(r.json().get('plan_required'), 'pro')

    def test_explain_endpoint_allowed_for_pro(self):
        self.client.force_login(self.pro)
        import json as _j

        r = self.client.post(
            '/api/ai/pipeline/explain/',
            data=_j.dumps({'scheme_data': self.demo_scheme}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('topology', data)
        # demo_scheme — RC-фильтр, pipeline должен классифицировать
        self.assertEqual(data['topology'], 'rc_filter')

    def test_recommend_endpoint_blocked_for_free(self):
        self.client.force_login(self.free)
        import json as _j

        r = self.client.post(
            '/api/ai/pipeline/recommend/',
            data=_j.dumps({'scheme_data': self.demo_scheme}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get('plan_required'), 'pro')

    @override_settings(ANTHROPIC_API_KEY='')
    def test_ai_chat_extended_mode_blocked_for_free_and_allowed_for_pro(self):
        import json as _j

        self.client.force_login(self.free)
        r = self.client.post(
            '/api/ai/chat/',
            data=_j.dumps({'mode': 'explain', 'message': 'Разбери схему'}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get('plan_required'), 'pro')

        self.client.force_login(self.pro)
        r = self.client.post(
            '/api/ai/chat/',
            data=_j.dumps({'mode': 'explain', 'message': 'Разбери схему'}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn('token_usage', r.json())


# ============================================================
# Comments
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class CommentsTests(TestCase):
    def setUp(self):
        self.free = _make_user('free_cmt')
        self.pro = _make_user('pro_cmt')
        activate_trial(self.pro)
        self.project = SchematicProject.objects.create(user=self.free, name='for-comments')

    def _post(self, user, body, project_id=None):
        self.client.force_login(user)
        import json as _j

        payload = {'body': body}
        if project_id:
            payload['project'] = project_id
        return self.client.post(
            '/api/comments/create/', data=_j.dumps(payload), content_type='application/json'
        )

    def test_free_comment_plain_text(self):
        r = self._post(self.free, 'Простой комментарий', project_id=self.project.id)
        self.assertEqual(r.status_code, 200)
        c = Comment.objects.get(id=r.json()['comment']['id'])
        self.assertFalse(c.is_rich)
        # render не должен интерпретировать Markdown
        html = c.render_html()
        self.assertNotIn('<h1>', html)

    def test_pro_comment_is_rich(self):
        r = self._post(self.pro, '# Title\n\n**bold**', project_id=self.project.id)
        self.assertEqual(r.status_code, 200)
        c = Comment.objects.get(id=r.json()['comment']['id'])
        self.assertTrue(c.is_rich)
        html = c.render_html()
        self.assertIn('<h1>', html)
        self.assertIn('<strong>bold</strong>', html)

    def test_xss_sanitized(self):
        """bleach удаляет опасные теги, текст оставляет как plain.
        Браузер не выполнит JS из <p>alert(1)</p> — это безопасно.
        """
        r = self._post(self.pro, '<script>alert(1)</script>**ok**', project_id=self.project.id)
        self.assertEqual(r.status_code, 200)
        c = Comment.objects.get(id=r.json()['comment']['id'])
        html = c.render_html()
        # Тег <script> должен быть удалён (главная защита от XSS)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<script', html.lower())
        # Markdown bold всё ещё работает
        self.assertIn('<strong>ok</strong>', html)

    def test_free_comment_max_500_chars(self):
        long_body = 'x' * 501
        r = self._post(self.free, long_body, project_id=self.project.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json().get('error'), 'too_long')

    def test_pro_comment_up_to_5000(self):
        body = 'x' * 4999
        r = self._post(self.pro, body, project_id=self.project.id)
        self.assertEqual(r.status_code, 200)


# ============================================================
# Pro-badge в UI
# ============================================================
@override_settings(ALLOWED_HOSTS=['*'])
class ProBadgeUITests(TestCase):
    def test_navbar_shows_pro_badge_for_pro(self):
        user = _make_user('pro_ui')
        activate_trial(user)
        self.client.force_login(user)
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode('utf-8')
        self.assertIn('nav-pro-badge', html)

    def test_navbar_shows_upgrade_link_for_free(self):
        user = _make_user('free_ui')
        self.client.force_login(user)
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)
        html = r.content.decode('utf-8')
        self.assertIn('nav-upgrade-link', html)

    def test_navbar_no_upgrade_for_pro(self):
        user = _make_user('pro_ui_2')
        activate_trial(user)
        self.client.force_login(user)
        r = self.client.get('/')
        html = r.content.decode('utf-8')
        self.assertNotIn('nav-upgrade-link', html)
