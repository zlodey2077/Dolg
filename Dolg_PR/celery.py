import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dolg_PR.settings')

app = Celery('Dolg_PR')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
