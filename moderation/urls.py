from django.urls import path

from Dolg_PR.url_utils import lazy_view

app_name = 'moderation'

urlpatterns = [
    path('moderation/', lazy_view('moderation.views.moderation_dashboard'), name='dashboard'),
    path('api/moderation/queue/', lazy_view('moderation.views.api_queue'), name='api_queue'),
    path('api/moderation/report/', lazy_view('moderation.views.api_report'), name='api_report'),
    path(
        'api/moderation/cases/<int:case_id>/action/',
        lazy_view('moderation.views.api_case_action'),
        name='api_case_action',
    ),
]
