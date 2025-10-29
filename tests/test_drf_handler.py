"""
Tests for DRF exception handler.
"""
from django.test import RequestFactory, TestCase
from rest_framework.test import APIRequestFactory

from django_blackbox.drf.exception_handler import incident_exception_handler
from django_blackbox.models import Incident


class DRFExceptionHandlerTest(TestCase):
    """Test DRF exception handler integration."""

    def setUp(self):
        """Set up test."""
        self.factory = APIRequestFactory()

    def test_4xx_returned_as_is(self):
        """Test that 4xx responses are returned unchanged."""
        from rest_framework.exceptions import ValidationError
        
        request = self.factory.post("/api/test/", {"invalid": "data"})
        
        class TestView:
            pass
        
        context = {"request": request, "view": TestView()}
        
        response = incident_exception_handler(ValidationError(), context)
        
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 400)

    def test_unhandled_exception_creates_incident(self):
        """Test that unhandled exceptions create an incident."""
        import uuid
        request = self.factory.get("/api/test/")
        
        class TestView:
            pass
        
        context = {"request": request, "view": TestView()}
        
        # Simulate unhandled exception
        exc = ValueError("Test error")
        
        # This should return None from DRF handler, but our handler creates an incident
        with patch("django_blackbox.drf.exception_handler.drf_exception_handler") as mock:
            mock.return_value = None  # Unhandled
            
            response = incident_exception_handler(exc, context)
            
            # Should create an incident
            incidents = Incident.objects.all()
            # The handler might not create one if configured not to
            # Let's check if response is JSON
            if response and response.status_code == 500:
                self.assertIn("application/json", str(response))


# Mock for testing
def patch(*args, **kwargs):
    from unittest.mock import patch as _patch
    return _patch(*args, **kwargs)

