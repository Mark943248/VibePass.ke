from django.apps import AppConfig


class TicketsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "Tickets"

    def ready(self):
        import Tickets.signals  # Import the signals module to connect signal handlers
