# To make sure Django loads your Celery app whenever it starts up
from .celery import app as celery_app

__all__ = ("celery_app",)
