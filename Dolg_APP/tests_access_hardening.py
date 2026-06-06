import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from Dolg_APP.models import Comment, SchematicProject

User = get_user_model()


@override_settings(ALLOWED_HOSTS=['*'])
class AccessHardeningTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user('audit_alice', 'alice@example.test', 'pw')
        self.bob = User.objects.create_user('audit_bob', 'bob@example.test', 'pw')
        self.private_project = SchematicProject.objects.create(
            user=self.alice,
            name='Private draft',
            visibility='private',
            scheme_data={'components': [], 'connections': []},
        )

    def test_private_project_comments_require_project_access(self):
        Comment.objects.create(
            user=self.alice,
            project=self.private_project,
            body='private note',
        )

        self.client.force_login(self.bob)
        response = self.client.get(f'/api/comments/?project={self.private_project.id}')

        self.assertEqual(response.status_code, 404)

    def test_private_project_comment_create_requires_project_access(self):
        self.client.force_login(self.bob)
        response = self.client.post(
            '/api/comments/create/',
            data=json.dumps({'project': self.private_project.id, 'body': 'hello'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Comment.objects.filter(project=self.private_project).count(), 0)

    def test_heavy_inline_endpoints_require_login(self):
        payload = {'scheme_data': {'components': [{'id': 'R1', 'type': 'resistor'}], 'connections': []}}
        endpoints = [
            '/simulation/api/export/pdf/',
            '/api/sim/monte_carlo/',
            '/api/sim/export/circuit_python/',
            '/api/sim/engineering_review/',
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(
                    endpoint,
                    data=json.dumps(payload),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 302)
                self.assertIn('/accounts/login', response.url)

    def test_free_user_cannot_use_duplicate_monte_carlo_endpoint(self):
        self.client.force_login(self.bob)
        response = self.client.post(
            '/api/sim/monte_carlo/',
            data=json.dumps(
                {
                    'scheme_data': {'components': [{'id': 'R1', 'type': 'resistor'}], 'connections': []},
                    'iterations': 10,
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json().get('error'), 'plan_required')

    def test_read_only_project_user_cannot_create_review(self):
        public_project = SchematicProject.objects.create(
            user=self.alice,
            name='Public read-only',
            visibility='public',
            scheme_data={'components': [{'id': 'R1', 'type': 'resistor'}], 'connections': []},
        )

        self.client.force_login(self.bob)
        response = self.client.post(f'/projects/api/{public_project.id}/review/')

        self.assertEqual(response.status_code, 404)

    def test_latest_review_does_not_create_for_read_only_user(self):
        public_project = SchematicProject.objects.create(
            user=self.alice,
            name='Public without review',
            visibility='public',
            scheme_data={'components': [{'id': 'R1', 'type': 'resistor'}], 'connections': []},
        )

        self.client.force_login(self.bob)
        response = self.client.get(f'/projects/api/{public_project.id}/review/latest/')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(public_project.reviews.count(), 0)

    def test_other_user_cannot_load_private_project_scheme(self):
        """IDOR: Bob не должен читать схему приватного проекта Alice."""
        self.client.force_login(self.bob)
        response = self.client.get(f'/projects/api/{self.private_project.id}/load-scheme/')
        self.assertEqual(response.status_code, 404)

    def test_owner_can_load_own_private_project_scheme(self):
        """Позитивный контроль: владелец читает свой проект."""
        self.client.force_login(self.alice)
        response = self.client.get(f'/projects/api/{self.private_project.id}/load-scheme/')
        self.assertEqual(response.status_code, 200, response.content)

    def test_other_user_cannot_save_private_project_scheme(self):
        """IDOR: Bob не должен перезаписывать схему приватного проекта Alice."""
        self.client.force_login(self.bob)
        response = self.client.post(
            f'/projects/api/{self.private_project.id}/save-scheme/',
            data=json.dumps(
                {'scheme_data': {'components': [{'id': 'X', 'type': 'resistor'}], 'connections': []}}
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
        self.private_project.refresh_from_db()
        self.assertEqual(self.private_project.scheme_data, {'components': [], 'connections': []})

    def test_other_user_cannot_update_private_project(self):
        """IDOR: Bob не должен править метаданные приватного проекта Alice."""
        self.client.force_login(self.bob)
        response = self.client.post(
            f'/projects/api/{self.private_project.id}/update/',
            data=json.dumps({'name': 'hijacked'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
        self.private_project.refresh_from_db()
        self.assertEqual(self.private_project.name, 'Private draft')

    def test_other_user_cannot_read_private_project_review(self):
        """IDOR: Bob не должен открывать review приватного проекта Alice."""
        from Dolg_APP.models import ProjectReview

        review = ProjectReview.objects.create(project=self.private_project, user=self.alice)
        self.client.force_login(self.bob)
        response = self.client.get(f'/projects/review/{review.id}/')
        self.assertEqual(response.status_code, 404)

    def test_save_scheme_persists_draft_with_drc_errors(self):
        self.client.force_login(self.alice)
        broken_scheme = {
            'components': [{'id': 'R1', 'type': 'resistor'}],
            'connections': [
                {'from': {'compId': 'R1', 'portId': '1'}, 'to': {'compId': 'MISSING', 'portId': '1'}},
            ],
        }

        response = self.client.post(
            f'/projects/api/{self.private_project.id}/save-scheme/',
            data=json.dumps({'scheme_data': broken_scheme}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertFalse(data['drc']['ok'])
        self.private_project.refresh_from_db()
        self.assertEqual(self.private_project.scheme_data, broken_scheme)
