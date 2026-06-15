from django.urls import path

from . import (
    chat_views,
    ml_admin_views,
    org_views,
    sso_views,
    two_factor_views,
    views,
    views_blocks,
)

app_name = 'hello'

urlpatterns = [
    # Tools for authorized users
    path('simulation/', views.simulation, name='simulation'),
    # 2026-06-02 фикс бага: «Новости» в nav вели на Энциклопедию (заглушка).
    path('news/', views.news, name='news'),
    path('simulation/ar/', views.ar_viewer, name='ar_viewer'),
    # Admin-only: тренировка нейронки прямо с сайта (background thread + polling).
    # ВАЖНО: префикс staff/, а НЕ admin/ — последний перехвачен django.contrib.admin
    # в корневом urls.py и наши вложенные пути не доходят (404).
    path('staff/ops/', ml_admin_views.staff_ops_dashboard, name='staff_ops_dashboard'),
    path('staff/ops/api/snapshot/', ml_admin_views.staff_ops_snapshot_api, name='staff_ops_snapshot_api'),
    path('staff/ml-training/', ml_admin_views.ml_training_page, name='ml_training_page'),
    path('staff/ml-dataset/', ml_admin_views.ml_dataset_quality_page, name='ml_dataset_quality_page'),
    path('staff/ml-training/start/', ml_admin_views.ml_training_start, name='ml_training_start'),
    path('staff/ml-training/status/', ml_admin_views.ml_training_status, name='ml_training_status'),
    path('staff/ml-training/reset/', ml_admin_views.ml_training_reset, name='ml_training_reset'),
    path('staff/ml-training/import/', ml_admin_views.ml_dataset_import, name='ml_dataset_import'),
    path(
        'staff/ml-training/import/status/',
        ml_admin_views.ml_dataset_import_status,
        name='ml_dataset_import_status',
    ),
    path('cad/', views.cad, name='cad'),
    path('projects/', views.projects, name='projects'),
    path('learn/', views.learn, name='learn'),
    path('pcb/<int:project_id>/', views.pcb_view, name='pcb_view'),
    path('pcb/<int:project_id>/gerber.zip', views.pcb_gerber_download, name='pcb_gerber_download'),
    path('pcb/<int:project_id>/autoroute/', views.api_pcb_autoroute, name='api_pcb_autoroute'),
    path('s/<str:token>/', views.shared_scheme, name='shared_scheme'),
    # Projects JSON API
    path('projects/api/list/', views.api_projects_list, name='api_projects_list'),
    # 2026-06-02 Lithium ECAD killer: Functional Blocks API
    path('api/blocks/', views_blocks.api_blocks_list, name='api_blocks_list'),
    path('api/blocks/create/', views_blocks.api_blocks_create, name='api_blocks_create'),
    path('api/blocks/<int:block_id>/', views_blocks.api_blocks_detail, name='api_blocks_detail'),
    path('api/blocks/<int:block_id>/use/', views_blocks.api_blocks_use, name='api_blocks_use'),
    path('api/blocks/<int:block_id>/delete/', views_blocks.api_blocks_delete, name='api_blocks_delete'),
    path('projects/api/create/', views.api_project_create, name='api_project_create'),
    path('projects/api/<int:pk>/update/', views.api_project_update, name='api_project_update'),
    path('projects/api/<int:pk>/delete/', views.api_project_delete, name='api_project_delete'),
    path('projects/api/<int:pk>/restore/', views.api_project_restore, name='api_project_restore'),
    path('projects/api/<int:pk>/purge/', views.api_project_purge, name='api_project_purge'),
    path('projects/api/trash/', views.api_project_trash_list, name='api_project_trash_list'),
    path('projects/api/<int:pk>/save-scheme/', views.api_project_save_scheme, name='api_project_save_scheme'),
    path('projects/api/<int:pk>/share/', views.api_project_share_toggle, name='api_project_share_toggle'),
    path('projects/api/<int:pk>/load-scheme/', views.api_project_load_scheme, name='api_project_load_scheme'),
    path('projects/api/<int:pk>/versions/', views.api_project_versions, name='api_project_versions'),
    path('projects/api/<int:pk>/dashboard/', views.api_project_dashboard, name='api_project_dashboard'),
    path(
        'projects/api/<int:pk>/simulation-runs/',
        views.api_project_simulation_runs,
        name='api_project_simulation_runs',
    ),
    path(
        'projects/api/<int:pk>/simulation-runs/stats/',
        views.api_project_simulation_stats,
        name='api_project_simulation_stats',
    ),
    path(
        'projects/api/<int:pk>/save-simulation/',
        views.api_project_save_simulation,
        name='api_project_save_simulation',
    ),
    path(
        'projects/api/<int:pk>/simulation/postprocess/',
        views.api_project_simulation_postprocess,
        name='api_project_simulation_postprocess',
    ),
    path(
        'projects/api/<int:pk>/simulation/<int:run_id>/export.csv',
        views.api_project_simulation_export_csv,
        name='api_project_simulation_export_csv',
    ),
    path(
        'projects/api/<int:pk>/measurements/', views.api_project_measurements, name='api_project_measurements'
    ),
    path(
        'projects/api/<int:pk>/measurements/create/',
        views.api_project_measurement_create,
        name='api_project_measurement_create',
    ),
    path('projects/api/<int:pk>/review/', views.api_project_review_create, name='api_project_review_create'),
    path(
        'projects/api/<int:pk>/review/latest/',
        views.api_project_review_latest,
        name='api_project_review_latest',
    ),
    path('projects/review/<int:review_id>/', views.project_review_page, name='project_review_page'),
    path('projects/review/<int:review_id>.pdf', views.project_review_pdf, name='project_review_pdf'),
    path('projects/review/<int:review_id>.md', views.project_review_md, name='project_review_md'),
    path('simulation/api/pro/fft/', views.api_simulation_fft, name='api_simulation_fft'),
    path('simulation/api/pro/bode/', views.api_simulation_bode, name='api_simulation_bode'),
    path(
        'simulation/api/pro/monte-carlo/', views.api_simulation_monte_carlo, name='api_simulation_monte_carlo'
    ),
    path(
        'simulation/api/pro/signal-quality/',
        views.api_simulation_signal_quality,
        name='api_simulation_signal_quality',
    ),
    path(
        'simulation/api/pro/parameter-sweep/',
        views.api_simulation_parameter_sweep,
        name='api_simulation_parameter_sweep',
    ),
    path(
        'simulation/api/fallback-solve/',
        views.api_simulation_fallback_solve,
        name='api_simulation_fallback_solve',
    ),
    path('simulation/api/export/pdf/', views.api_export_scheme_pdf, name='api_export_scheme_pdf'),
    path('cad/api/convert-dwg/', views.api_cad_convert_dwg, name='api_cad_convert_dwg'),
    path(
        'cad/api/scheme/operations/preview/',
        views.api_cad_scheme_operations_preview,
        name='api_cad_scheme_operations_preview',
    ),
    path('cad/api/import/', views.api_cad_import_preview, name='api_cad_import_preview'),
    path('cad/api/lithium-import/', views.api_lithium_import_preview, name='api_lithium_import_preview'),
    # AI-ассистент DOLG (чат с Claude)
    path('api/ai/chat/', views.api_ai_chat, name='api_ai_chat'),
    path('api/ai/context/', views.api_ai_context, name='api_ai_context'),
    # Engineering Review V2: in-memory scheme → JSON-отчёт (no project save).
    path('api/sim/engineering_review/', views.api_engineering_review, name='api_engineering_review'),
    # Авто-протокол (Markdown): инженерный отчёт / протокол лабораторной работы.
    path('api/sim/protocol/', views.api_generate_protocol, name='api_generate_protocol'),
    # Block B1: schema → CircuitPython code.py для прошивки микроконтроллеров.
    path('api/sim/export/circuit_python/', views.api_export_circuit_python, name='api_export_circuit_python'),
    # Block D2: server-side Monte Carlo DC analysis (numpy MNA, 1000+ iter/sec).
    path('api/sim/monte_carlo/', views.api_monte_carlo, name='api_monte_carlo'),
    # RF S-параметры 2-портовых фильтров через scikit-rf (S21/S11, −3дБ).
    path('api/sim/rf_analysis/', views.api_rf_analysis, name='api_rf_analysis'),
    # Usage stats — для UI-баннеров «15/20 today»
    path('api/usage/today/', views.api_usage_today, name='api_usage_today'),
    # Legal pages
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('cookies/', views.cookies, name='cookies'),
    # Billing / Pro-subscription (mock — без реальной оплаты)
    path('billing/', views.billing_plans, name='billing_plans'),
    path('billing/trial/', views.billing_activate_trial, name='billing_activate_trial'),
    path('billing/activate/', views.billing_activate_pro, name='billing_activate_pro'),
    path('billing/cancel/', views.billing_cancel, name='billing_cancel'),
    # Stripe Checkout: success-redirect после успешной оплаты
    path('billing/success/', views.billing_checkout_success, name='billing_checkout_success'),
    # Stripe webhook (separate от orders.payment_views.stripe_webhook):
    # этот для Pro-подписок, тот — для одноразовых Order платежей.
    path('billing/stripe-webhook/', views.billing_stripe_webhook, name='billing_stripe_webhook'),
    # AI pipeline (Phase 1: rule-based heuristics)
    # Free: find_analogs, detect_anomalies. Pro: + explain_scheme, recommend_next.
    path('api/ai/pipeline/info/', views.api_ai_pipeline_info, name='api_ai_pipeline_info'),
    path('api/ai/pipeline/analogs/', views.api_ai_find_analogs, name='api_ai_find_analogs'),
    path('api/ai/pipeline/anomalies/', views.api_ai_detect_anomalies, name='api_ai_detect_anomalies'),
    path('api/ai/pipeline/explain/', views.api_ai_explain_scheme, name='api_ai_explain_scheme'),
    path('api/ai/pipeline/recommend/', views.api_ai_recommend_next, name='api_ai_recommend_next'),
    # Comments — Free plain-text, Pro Markdown с code-highlight
    path('api/comments/', views.api_comments_list, name='api_comments_list'),
    path('api/comments/create/', views.api_comments_create, name='api_comments_create'),
    path('api/comments/<int:pk>/delete/', views.api_comments_delete, name='api_comments_delete'),
    # Enterprise: Organizations
    path('orgs/', org_views.org_list, name='org_list'),
    path('orgs/create/', org_views.org_create, name='org_create'),
    path('orgs/<slug:org_slug>/', org_views.org_dashboard, name='org_dashboard'),
    path('orgs/<slug:org_slug>/members/', org_views.org_members, name='org_members'),
    path('orgs/<slug:org_slug>/members/invite/', org_views.org_invite_create, name='org_invite_create'),
    path(
        'orgs/<slug:org_slug>/members/<int:member_id>/role/',
        org_views.org_member_role,
        name='org_member_role',
    ),
    path(
        'orgs/<slug:org_slug>/members/<int:member_id>/remove/',
        org_views.org_member_remove,
        name='org_member_remove',
    ),
    path('orgs/<slug:org_slug>/invite/<str:token>/', org_views.org_invite_accept, name='org_invite_accept'),
    path('orgs/<slug:org_slug>/settings/', org_views.org_settings, name='org_settings'),
    path('orgs/<slug:org_slug>/audit/', org_views.org_audit, name='org_audit'),
    # Catalog: Enterprise-member может предложить товар в общий каталог
    path('orgs/<slug:org_slug>/catalog/add/', org_views.org_catalog_add, name='org_catalog_add'),
    path('orgs/<slug:org_slug>/approval/', org_views.org_approval_queue, name='org_approval_queue'),
    path(
        'orgs/<slug:org_slug>/projects/<int:pk>/submit/',
        org_views.project_submit_for_review,
        name='project_submit_for_review',
    ),
    path(
        'orgs/<slug:org_slug>/projects/<int:pk>/approve/', org_views.project_approve, name='project_approve'
    ),
    path('orgs/<slug:org_slug>/projects/<int:pk>/reject/', org_views.project_reject, name='project_reject'),
    # Mock SSO для Enterprise (для real SSO см. django-allauth /accounts/social/)
    path('sso/<slug:org_slug>/redirect/', sso_views.sso_redirect, name='sso_redirect'),
    path('sso/<slug:org_slug>/callback/', sso_views.sso_callback, name='sso_callback'),
    # 2FA: TOTP enrollment + login challenge + backup-коды
    path('2fa/setup/', two_factor_views.two_factor_setup, name='two_factor_setup'),
    path('2fa/verify/', two_factor_views.two_factor_verify, name='two_factor_verify'),
    path('2fa/disable/', two_factor_views.two_factor_disable, name='two_factor_disable'),
    path('2fa/backup/', two_factor_views.two_factor_backup_codes_view, name='two_factor_backup_codes'),
    path(
        '2fa/backup/regenerate/',
        two_factor_views.two_factor_backup_codes_regenerate,
        name='two_factor_backup_regenerate',
    ),
    # Org analytics + API tokens
    path('orgs/<slug:org_slug>/analytics/', org_views.org_analytics, name='org_analytics'),
    path('orgs/<slug:org_slug>/api-tokens/', org_views.org_api_tokens, name='org_api_tokens'),
    path(
        'orgs/<slug:org_slug>/api-tokens/create/', org_views.org_api_token_create, name='org_api_token_create'
    ),
    path(
        'orgs/<slug:org_slug>/api-tokens/<int:token_id>/revoke/',
        org_views.org_api_token_revoke,
        name='org_api_token_revoke',
    ),
    # Public Q&A чат — для всех (guest read-only, registered+ write)
    path('chat/', chat_views.chat_list, name='chat_list'),
    path('chat/new/', chat_views.chat_topic_create, name='chat_topic_create'),
    path('chat/<int:topic_id>/', chat_views.chat_topic_detail, name='chat_topic_detail'),
    path('chat/<int:topic_id>/reply/', chat_views.chat_reply_create, name='chat_reply_create'),
    path('chat/<int:topic_id>/pin/', chat_views.chat_topic_pin_toggle, name='chat_topic_pin_toggle'),
    path(
        'chat/<int:topic_id>/reply/<int:reply_id>/accept/',
        chat_views.chat_reply_accept_answer,
        name='chat_reply_accept_answer',
    ),
    path('chat/<int:topic_id>/poll/', chat_views.chat_topic_poll, name='chat_topic_poll'),
    path('chat/react/', chat_views.chat_reaction_toggle, name='chat_reaction_toggle'),
    # Org беседы — приватные каналы Enterprise
    path(
        'orgs/<slug:org_slug>/conversations/', chat_views.org_conversation_list, name='org_conversation_list'
    ),
    path(
        'orgs/<slug:org_slug>/conversations/new/',
        chat_views.org_conversation_create,
        name='org_conversation_create',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/<int:conv_id>/',
        chat_views.org_conversation_detail,
        name='org_conversation_detail',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/<int:conv_id>/message/',
        chat_views.org_conversation_message_create,
        name='org_conversation_message_create',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/<int:conv_id>/archive/',
        chat_views.org_conversation_archive,
        name='org_conversation_archive',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/<int:conv_id>/poll/',
        chat_views.org_conversation_poll,
        name='org_conversation_poll',
    ),
]
