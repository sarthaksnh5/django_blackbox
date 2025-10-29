from django.apps import AppConfig


class DjangoBlackboxConfig(AppConfig):
    """App configuration for django_blackbox."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "django_blackbox"
    verbose_name = "Django Black Box"

