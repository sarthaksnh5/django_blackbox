"""
URL patterns for the read-only API.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import IncidentViewSet

# Create a router and register the viewset
router = DefaultRouter()
router.register(r"incidents", IncidentViewSet, basename="incident")

app_name = "django_blackbox_api"

urlpatterns = [
    path("", include(router.urls)),
]

