import os
from celery import Celery


# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'VibePassApp.settings')

# This variable MUST be named 'app'
app = Celery('VibePassApp')

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()