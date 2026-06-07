from celery import shared_task


@shared_task
def container_worker_ping():
    """Tiny smoke task for the Docker/Celery worker pipeline."""
    return 'pong'
