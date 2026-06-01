from django.urls import path

from . import views

app_name = 'moderation'

urlpatterns = [
    path('moderation/', views.moderation_dashboard, name='dashboard'),
    path('api/moderation/queue/', views.api_queue, name='api_queue'),
    path('api/moderation/report/', views.api_report, name='api_report'),
    path('api/moderation/cases/<int:case_id>/action/', views.api_case_action, name='api_case_action'),
]
