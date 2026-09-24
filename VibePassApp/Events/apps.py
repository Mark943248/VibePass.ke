from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "Events"

    def ready(self):
        import Events.signals  # noqa: F401
