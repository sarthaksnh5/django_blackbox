from django.apps import AppConfig


class DjangoBlackboxConfig(AppConfig):
    """App configuration for django_blackbox."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_blackbox"
    verbose_name = "Django Black Box"

    def ready(self):
        """Register signal handlers when app is ready."""
        # Import activity tracking to register signal handlers
        from . import activity_tracking  # noqa: F401

