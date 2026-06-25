from django.urls import path

from Dolg_PR.url_utils import lazy_view

app_name = 'hello'

urlpatterns = [
    # Tools for authorized users
    path('simulation/', lazy_view('Dolg_APP.views.simulation'), name='simulation'),
    # 2026-06-02 фикс бага: «Новости» в nav вели на Энциклопедию (заглушка).
    path('news/', lazy_view('Dolg_APP.views.news'), name='news'),
    path('simulation/ar/', lazy_view('Dolg_APP.views.ar_viewer'), name='ar_viewer'),
    # Admin-only: тренировка нейронки прямо с сайта (background thread + polling).
    # ВАЖНО: префикс staff/, а НЕ admin/ — последний перехвачен django.contrib.admin
    # в корневом urls.py и наши вложенные пути не доходят (404).
    path('staff/ops/', lazy_view('Dolg_APP.ml_admin_views.staff_ops_dashboard'), name='staff_ops_dashboard'),
    path(
        'staff/data-console/',
        lazy_view('Dolg_APP.ml_admin_views.staff_data_console'),
        name='staff_data_console',
    ),
    path(
        'staff/ops/api/snapshot/',
        lazy_view('Dolg_APP.ml_admin_views.staff_ops_snapshot_api'),
        name='staff_ops_snapshot_api',
    ),
    path(
        'staff/ml-training/', lazy_view('Dolg_APP.ml_admin_views.ml_training_page'), name='ml_training_page'
    ),
    path(
        'staff/ml-dataset/',
        lazy_view('Dolg_APP.ml_admin_views.ml_dataset_quality_page'),
        name='ml_dataset_quality_page',
    ),
    path(
        'staff/ml-training/start/',
        lazy_view('Dolg_APP.ml_admin_views.ml_training_start'),
        name='ml_training_start',
    ),
    path(
        'staff/ml-training/status/',
        lazy_view('Dolg_APP.ml_admin_views.ml_training_status'),
        name='ml_training_status',
    ),
    path(
        'staff/ml-training/reset/',
        lazy_view('Dolg_APP.ml_admin_views.ml_training_reset'),
        name='ml_training_reset',
    ),
    path(
        'staff/ml-training/import/',
        lazy_view('Dolg_APP.ml_admin_views.ml_dataset_import'),
        name='ml_dataset_import',
    ),
    path(
        'staff/ml-training/import/status/',
        lazy_view('Dolg_APP.ml_admin_views.ml_dataset_import_status'),
        name='ml_dataset_import_status',
    ),
    path('cad/', lazy_view('Dolg_APP.views.cad'), name='cad'),
    path('projects/', lazy_view('Dolg_APP.views.projects'), name='projects'),
    path('learn/', lazy_view('Dolg_APP.views.learn'), name='learn'),
    path('pcb/<int:project_id>/', lazy_view('Dolg_APP.views.pcb_view'), name='pcb_view'),
    path(
        'pcb/<int:project_id>/gerber.zip',
        lazy_view('Dolg_APP.views.pcb_gerber_download'),
        name='pcb_gerber_download',
    ),
    path(
        'pcb/<int:project_id>/autoroute/',
        lazy_view('Dolg_APP.views.api_pcb_autoroute'),
        name='api_pcb_autoroute',
    ),
    path('s/<str:token>/', lazy_view('Dolg_APP.views.shared_scheme'), name='shared_scheme'),
    # Projects JSON API
    path('projects/api/list/', lazy_view('Dolg_APP.views.api_projects_list'), name='api_projects_list'),
    # 2026-06-02 Lithium ECAD killer: Functional Blocks API
    path('api/blocks/', lazy_view('Dolg_APP.views_blocks.api_blocks_list'), name='api_blocks_list'),
    path(
        'api/blocks/create/', lazy_view('Dolg_APP.views_blocks.api_blocks_create'), name='api_blocks_create'
    ),
    path(
        'api/blocks/<int:block_id>/',
        lazy_view('Dolg_APP.views_blocks.api_blocks_detail'),
        name='api_blocks_detail',
    ),
    path(
        'api/blocks/<int:block_id>/use/',
        lazy_view('Dolg_APP.views_blocks.api_blocks_use'),
        name='api_blocks_use',
    ),
    path(
        'api/blocks/<int:block_id>/delete/',
        lazy_view('Dolg_APP.views_blocks.api_blocks_delete'),
        name='api_blocks_delete',
    ),
    path('projects/api/create/', lazy_view('Dolg_APP.views.api_project_create'), name='api_project_create'),
    path(
        'projects/api/<int:pk>/update/',
        lazy_view('Dolg_APP.views.api_project_update'),
        name='api_project_update',
    ),
    path(
        'projects/api/<int:pk>/delete/',
        lazy_view('Dolg_APP.views.api_project_delete'),
        name='api_project_delete',
    ),
    path(
        'projects/api/<int:pk>/restore/',
        lazy_view('Dolg_APP.views.api_project_restore'),
        name='api_project_restore',
    ),
    path(
        'projects/api/<int:pk>/purge/',
        lazy_view('Dolg_APP.views.api_project_purge'),
        name='api_project_purge',
    ),
    path(
        'projects/api/trash/',
        lazy_view('Dolg_APP.views.api_project_trash_list'),
        name='api_project_trash_list',
    ),
    path(
        'projects/api/<int:pk>/save-scheme/',
        lazy_view('Dolg_APP.views.api_project_save_scheme'),
        name='api_project_save_scheme',
    ),
    path(
        'projects/api/<int:pk>/share/',
        lazy_view('Dolg_APP.views.api_project_share_toggle'),
        name='api_project_share_toggle',
    ),
    path(
        'projects/api/<int:pk>/load-scheme/',
        lazy_view('Dolg_APP.views.api_project_load_scheme'),
        name='api_project_load_scheme',
    ),
    path(
        'projects/api/<int:pk>/versions/',
        lazy_view('Dolg_APP.views.api_project_versions'),
        name='api_project_versions',
    ),
    path(
        'projects/api/<int:pk>/dashboard/',
        lazy_view('Dolg_APP.views.api_project_dashboard'),
        name='api_project_dashboard',
    ),
    path(
        'projects/api/<int:pk>/simulation-runs/',
        lazy_view('Dolg_APP.views.api_project_simulation_runs'),
        name='api_project_simulation_runs',
    ),
    path(
        'projects/api/<int:pk>/simulation-runs/stats/',
        lazy_view('Dolg_APP.views.api_project_simulation_stats'),
        name='api_project_simulation_stats',
    ),
    path(
        'projects/api/<int:pk>/save-simulation/',
        lazy_view('Dolg_APP.views.api_project_save_simulation'),
        name='api_project_save_simulation',
    ),
    path(
        'projects/api/<int:pk>/simulation/postprocess/',
        lazy_view('Dolg_APP.views.api_project_simulation_postprocess'),
        name='api_project_simulation_postprocess',
    ),
    path(
        'projects/api/<int:pk>/simulation/<int:run_id>/export.csv',
        lazy_view('Dolg_APP.views.api_project_simulation_export_csv'),
        name='api_project_simulation_export_csv',
    ),
    path(
        'projects/api/<int:pk>/measurements/',
        lazy_view('Dolg_APP.views.api_project_measurements'),
        name='api_project_measurements',
    ),
    path(
        'projects/api/<int:pk>/measurements/create/',
        lazy_view('Dolg_APP.views.api_project_measurement_create'),
        name='api_project_measurement_create',
    ),
    path(
        'projects/api/<int:pk>/review/',
        lazy_view('Dolg_APP.views.api_project_review_create'),
        name='api_project_review_create',
    ),
    path(
        'projects/api/<int:pk>/review/latest/',
        lazy_view('Dolg_APP.views.api_project_review_latest'),
        name='api_project_review_latest',
    ),
    path(
        'projects/review/<int:review_id>/',
        lazy_view('Dolg_APP.views.project_review_page'),
        name='project_review_page',
    ),
    path(
        'projects/review/<int:review_id>.pdf',
        lazy_view('Dolg_APP.views.project_review_pdf'),
        name='project_review_pdf',
    ),
    path(
        'projects/review/<int:review_id>.md',
        lazy_view('Dolg_APP.views.project_review_md'),
        name='project_review_md',
    ),
    path(
        'simulation/api/pro/fft/', lazy_view('Dolg_APP.views.api_simulation_fft'), name='api_simulation_fft'
    ),
    path(
        'simulation/api/voltage-field/',
        lazy_view('Dolg_APP.views.api_simulation_voltage_field'),
        name='api_simulation_voltage_field',
    ),
    path(
        'simulation/api/pro/bode/',
        lazy_view('Dolg_APP.views.api_simulation_bode'),
        name='api_simulation_bode',
    ),
    path(
        'simulation/api/pro/monte-carlo/',
        lazy_view('Dolg_APP.views.api_simulation_monte_carlo'),
        name='api_simulation_monte_carlo',
    ),
    path(
        'simulation/api/pro/signal-quality/',
        lazy_view('Dolg_APP.views.api_simulation_signal_quality'),
        name='api_simulation_signal_quality',
    ),
    path(
        'simulation/api/pro/parameter-sweep/',
        lazy_view('Dolg_APP.views.api_simulation_parameter_sweep'),
        name='api_simulation_parameter_sweep',
    ),
    path(
        'simulation/api/fallback-solve/',
        lazy_view('Dolg_APP.views.api_simulation_fallback_solve'),
        name='api_simulation_fallback_solve',
    ),
    path(
        'simulation/api/export/pdf/',
        lazy_view('Dolg_APP.views.api_export_scheme_pdf'),
        name='api_export_scheme_pdf',
    ),
    path('cad/api/convert-dwg/', lazy_view('Dolg_APP.views.api_cad_convert_dwg'), name='api_cad_convert_dwg'),
    path(
        'cad/api/scheme/operations/preview/',
        lazy_view('Dolg_APP.views.api_cad_scheme_operations_preview'),
        name='api_cad_scheme_operations_preview',
    ),
    path(
        'cad/api/import/', lazy_view('Dolg_APP.views.api_cad_import_preview'), name='api_cad_import_preview'
    ),
    path(
        'cad/api/lithium-import/',
        lazy_view('Dolg_APP.views.api_lithium_import_preview'),
        name='api_lithium_import_preview',
    ),
    # AI-ассистент DOLG (локальный Ollama/PyTorch/rule-based runtime)
    path('api/ai/chat/', lazy_view('Dolg_APP.views.api_ai_chat'), name='api_ai_chat'),
    path('api/ai/context/', lazy_view('Dolg_APP.views.api_ai_context'), name='api_ai_context'),
    # Engineering Review V2: in-memory scheme → JSON-отчёт (no project save).
    path(
        'api/sim/engineering_review/',
        lazy_view('Dolg_APP.views.api_engineering_review'),
        name='api_engineering_review',
    ),
    # Авто-протокол (Markdown): инженерный отчёт / протокол лабораторной работы.
    path(
        'api/sim/protocol/', lazy_view('Dolg_APP.views.api_generate_protocol'), name='api_generate_protocol'
    ),
    # Block B1: schema → CircuitPython code.py для прошивки микроконтроллеров.
    path(
        'api/sim/export/circuit_python/',
        lazy_view('Dolg_APP.views.api_export_circuit_python'),
        name='api_export_circuit_python',
    ),
    # Server-side engine router catalog: Xyce/PySpice/GnuCap/OpenModelica/etc.
    path(
        'api/sim/server-engines/', lazy_view('Dolg_APP.views.api_server_engines'), name='api_server_engines'
    ),
    path(
        'api/sim/server-engines/recommend/',
        lazy_view('Dolg_APP.views.api_server_engine_recommend'),
        name='api_server_engine_recommend',
    ),
    path('api/sim/jobs/', lazy_view('Dolg_APP.views.api_engine_jobs'), name='api_engine_jobs'),
    path(
        'api/sim/jobs/<int:job_id>/',
        lazy_view('Dolg_APP.views.api_engine_job_detail'),
        name='api_engine_job_detail',
    ),
    path(
        'api/sim/jobs/<int:job_id>/result/',
        lazy_view('Dolg_APP.views.api_engine_job_result'),
        name='api_engine_job_result',
    ),
    path(
        'api/sim/jobs/<int:job_id>/retry/',
        lazy_view('Dolg_APP.views.api_engine_job_retry'),
        name='api_engine_job_retry',
    ),
    # Block D2: server-side Monte Carlo DC analysis (numpy MNA, 1000+ iter/sec).
    path('api/sim/monte_carlo/', lazy_view('Dolg_APP.views.api_monte_carlo'), name='api_monte_carlo'),
    # RF S-параметры 2-портовых фильтров через scikit-rf (S21/S11, −3дБ).
    path('api/sim/rf_analysis/', lazy_view('Dolg_APP.views.api_rf_analysis'), name='api_rf_analysis'),
    # Usage stats — для UI-баннеров «15/20 today»
    path('api/usage/today/', lazy_view('Dolg_APP.views.api_usage_today'), name='api_usage_today'),
    # Legal pages
    path('terms/', lazy_view('Dolg_APP.views.terms'), name='terms'),
    path('privacy/', lazy_view('Dolg_APP.views.privacy'), name='privacy'),
    path('cookies/', lazy_view('Dolg_APP.views.cookies'), name='cookies'),
    # Billing / Pro-subscription (mock — без реальной оплаты)
    path('billing/', lazy_view('Dolg_APP.views.billing_plans'), name='billing_plans'),
    path('billing/trial/', lazy_view('Dolg_APP.views.billing_activate_trial'), name='billing_activate_trial'),
    path('billing/activate/', lazy_view('Dolg_APP.views.billing_activate_pro'), name='billing_activate_pro'),
    path('billing/cancel/', lazy_view('Dolg_APP.views.billing_cancel'), name='billing_cancel'),
    # Stripe Checkout: success-redirect после успешной оплаты
    path(
        'billing/success/',
        lazy_view('Dolg_APP.views.billing_checkout_success'),
        name='billing_checkout_success',
    ),
    # Stripe webhook (separate от orders.payment_lazy_view('Dolg_APP.views.stripe_webhook')):
    # этот для Pro-подписок, тот — для одноразовых Order платежей.
    path(
        'billing/stripe-webhook/',
        lazy_view('Dolg_APP.views.billing_stripe_webhook', csrf_exempt=True),
        name='billing_stripe_webhook',
    ),
    # AI pipeline (Phase 1: rule-based heuristics)
    # Free: find_analogs, detect_anomalies. Pro: + explain_scheme, recommend_next.
    path(
        'api/ai/pipeline/info/', lazy_view('Dolg_APP.views.api_ai_pipeline_info'), name='api_ai_pipeline_info'
    ),
    path(
        'api/ai/pipeline/analogs/',
        lazy_view('Dolg_APP.views.api_ai_find_analogs'),
        name='api_ai_find_analogs',
    ),
    path(
        'api/ai/pipeline/anomalies/',
        lazy_view('Dolg_APP.views.api_ai_detect_anomalies'),
        name='api_ai_detect_anomalies',
    ),
    path(
        'api/ai/pipeline/explain/',
        lazy_view('Dolg_APP.views.api_ai_explain_scheme'),
        name='api_ai_explain_scheme',
    ),
    path(
        'api/ai/pipeline/recommend/',
        lazy_view('Dolg_APP.views.api_ai_recommend_next'),
        name='api_ai_recommend_next',
    ),
    # Comments — Free plain-text, Pro Markdown с code-highlight
    path('api/comments/', lazy_view('Dolg_APP.views.api_comments_list'), name='api_comments_list'),
    path('api/comments/create/', lazy_view('Dolg_APP.views.api_comments_create'), name='api_comments_create'),
    path(
        'api/comments/<int:pk>/delete/',
        lazy_view('Dolg_APP.views.api_comments_delete'),
        name='api_comments_delete',
    ),
    # Enterprise: Organizations
    path('orgs/', lazy_view('Dolg_APP.org_views.org_list'), name='org_list'),
    path('orgs/create/', lazy_view('Dolg_APP.org_views.org_create'), name='org_create'),
    path('orgs/<slug:org_slug>/', lazy_view('Dolg_APP.org_views.org_dashboard'), name='org_dashboard'),
    path('orgs/<slug:org_slug>/members/', lazy_view('Dolg_APP.org_views.org_members'), name='org_members'),
    path(
        'orgs/<slug:org_slug>/members/invite/',
        lazy_view('Dolg_APP.org_views.org_invite_create'),
        name='org_invite_create',
    ),
    path(
        'orgs/<slug:org_slug>/members/<int:member_id>/role/',
        lazy_view('Dolg_APP.org_views.org_member_role'),
        name='org_member_role',
    ),
    path(
        'orgs/<slug:org_slug>/members/<int:member_id>/remove/',
        lazy_view('Dolg_APP.org_views.org_member_remove'),
        name='org_member_remove',
    ),
    path(
        'orgs/<slug:org_slug>/invite/<str:token>/',
        lazy_view('Dolg_APP.org_views.org_invite_accept'),
        name='org_invite_accept',
    ),
    path('orgs/<slug:org_slug>/settings/', lazy_view('Dolg_APP.org_views.org_settings'), name='org_settings'),
    path('orgs/<slug:org_slug>/audit/', lazy_view('Dolg_APP.org_views.org_audit'), name='org_audit'),
    # Catalog: Enterprise-member может предложить товар в общий каталог
    path(
        'orgs/<slug:org_slug>/catalog/add/',
        lazy_view('Dolg_APP.org_views.org_catalog_add'),
        name='org_catalog_add',
    ),
    path(
        'orgs/<slug:org_slug>/approval/',
        lazy_view('Dolg_APP.org_views.org_approval_queue'),
        name='org_approval_queue',
    ),
    path(
        'orgs/<slug:org_slug>/projects/<int:pk>/submit/',
        lazy_view('Dolg_APP.org_views.project_submit_for_review'),
        name='project_submit_for_review',
    ),
    path(
        'orgs/<slug:org_slug>/projects/<int:pk>/approve/',
        lazy_view('Dolg_APP.org_views.project_approve'),
        name='project_approve',
    ),
    path(
        'orgs/<slug:org_slug>/projects/<int:pk>/reject/',
        lazy_view('Dolg_APP.org_views.project_reject'),
        name='project_reject',
    ),
    # Mock SSO для Enterprise (для real SSO см. django-allauth /accounts/social/)
    path('sso/<slug:org_slug>/redirect/', lazy_view('Dolg_APP.sso_views.sso_redirect'), name='sso_redirect'),
    path('sso/<slug:org_slug>/callback/', lazy_view('Dolg_APP.sso_views.sso_callback'), name='sso_callback'),
    # 2FA: TOTP enrollment + login challenge + backup-коды
    path('2fa/setup/', lazy_view('Dolg_APP.two_factor_views.two_factor_setup'), name='two_factor_setup'),
    path('2fa/verify/', lazy_view('Dolg_APP.two_factor_views.two_factor_verify'), name='two_factor_verify'),
    path(
        '2fa/disable/', lazy_view('Dolg_APP.two_factor_views.two_factor_disable'), name='two_factor_disable'
    ),
    path(
        '2fa/backup/',
        lazy_view('Dolg_APP.two_factor_views.two_factor_backup_codes_view'),
        name='two_factor_backup_codes',
    ),
    path(
        '2fa/backup/regenerate/',
        lazy_view('Dolg_APP.two_factor_views.two_factor_backup_codes_regenerate'),
        name='two_factor_backup_regenerate',
    ),
    # Org analytics + API tokens
    path(
        'orgs/<slug:org_slug>/analytics/', lazy_view('Dolg_APP.org_views.org_analytics'), name='org_analytics'
    ),
    path(
        'orgs/<slug:org_slug>/api-tokens/',
        lazy_view('Dolg_APP.org_views.org_api_tokens'),
        name='org_api_tokens',
    ),
    path(
        'orgs/<slug:org_slug>/api-tokens/create/',
        lazy_view('Dolg_APP.org_views.org_api_token_create'),
        name='org_api_token_create',
    ),
    path(
        'orgs/<slug:org_slug>/api-tokens/<int:token_id>/revoke/',
        lazy_view('Dolg_APP.org_views.org_api_token_revoke'),
        name='org_api_token_revoke',
    ),
    # Public Q&A чат — для всех (guest read-only, registered+ write)
    path('chat/', lazy_view('Dolg_APP.chat_views.chat_list'), name='chat_list'),
    path('chat/new/', lazy_view('Dolg_APP.chat_views.chat_topic_create'), name='chat_topic_create'),
    path(
        'chat/<int:topic_id>/', lazy_view('Dolg_APP.chat_views.chat_topic_detail'), name='chat_topic_detail'
    ),
    path(
        'chat/<int:topic_id>/reply/',
        lazy_view('Dolg_APP.chat_views.chat_reply_create'),
        name='chat_reply_create',
    ),
    path(
        'chat/<int:topic_id>/pin/',
        lazy_view('Dolg_APP.chat_views.chat_topic_pin_toggle'),
        name='chat_topic_pin_toggle',
    ),
    path(
        'chat/<int:topic_id>/reply/<int:reply_id>/accept/',
        lazy_view('Dolg_APP.chat_views.chat_reply_accept_answer'),
        name='chat_reply_accept_answer',
    ),
    path(
        'chat/<int:topic_id>/poll/', lazy_view('Dolg_APP.chat_views.chat_topic_poll'), name='chat_topic_poll'
    ),
    path('chat/react/', lazy_view('Dolg_APP.chat_views.chat_reaction_toggle'), name='chat_reaction_toggle'),
    # Org беседы — приватные каналы Enterprise
    path(
        'orgs/<slug:org_slug>/conversations/',
        lazy_view('Dolg_APP.chat_views.org_conversation_list'),
        name='org_conversation_list',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/new/',
        lazy_view('Dolg_APP.chat_views.org_conversation_create'),
        name='org_conversation_create',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/<int:conv_id>/',
        lazy_view('Dolg_APP.chat_views.org_conversation_detail'),
        name='org_conversation_detail',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/<int:conv_id>/message/',
        lazy_view('Dolg_APP.chat_views.org_conversation_message_create'),
        name='org_conversation_message_create',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/<int:conv_id>/archive/',
        lazy_view('Dolg_APP.chat_views.org_conversation_archive'),
        name='org_conversation_archive',
    ),
    path(
        'orgs/<slug:org_slug>/conversations/<int:conv_id>/poll/',
        lazy_view('Dolg_APP.chat_views.org_conversation_poll'),
        name='org_conversation_poll',
    ),
]
