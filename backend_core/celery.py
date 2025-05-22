import os

from celery import Celery
from celery.schedules import crontab
from django.conf import settings 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_core.settings')

app = Celery('backend_core')
# app.config_from_object('django.settings', namespace='CELERY')

app.config_from_object(settings, namespace='CELERY')
app.autodiscover_tasks() 

# Celery Beat Schedule for stale order detection
app.conf.beat_schedule = {
    'detect-stale-orders-every-minute': { # Name of the schedule
        'task': 'orders.tasks.detect_and_handle_stale_orders', # Task to run
        'schedule': crontab(minute='*/1'), # Run every minute for testing (adjust for prod)
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')