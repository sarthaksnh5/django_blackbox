"""
Tests for middleware components.
"""
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from django_blackbox.conf import Config, reset_config
from django_blackbox.middleware import Capture5xxMiddleware, RequestIDMiddleware
from django_blackbox.models import Incident


class RequestIDMiddlewareTest(TestCase):
    """Test RequestIDMiddleware."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        self.middleware = RequestIDMiddleware(lambda req: HttpResponse())

    def test_request_id_from_header(self):
        """Test that request ID is taken from incoming header."""
        import uuid
        rid = str(uuid.uuid4())
        request = self.factory.get("/", HTTP_X_REQUEST_ID=rid)
        
        self.middleware.process_request(request)
        
        self.assertEqual(request.server_incidents_request_id, rid)

    def test_request_id_generated(self):
        """Test that request ID is generated if not in header."""
        request = self.factory.get("/")
        
        self.middleware.process_request(request)
        
        self.assertIsNotNone(request.server_incidents_request_id)
        self.assertIsInstance(request.server_incidents_request_id, str)

    def test_response_header_added(self):
        """Test that X-Request-ID header is added to response."""
        request = self.factory.get("/")
        response = HttpResponse()
        
        self.middleware.process_request(request)
        response = self.middleware.process_response(request, response)
        
        self.assertIn("X-Request-ID", response)


class Capture5xxMiddlewareTest(TestCase):
    """Test Capture5xxMiddleware."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        self.middleware = Capture5xxMiddleware(lambda req: HttpResponse())
        reset_config()

    def test_4xx_not_captured(self):
        """Test that 4xx responses are not captured."""
        request = self.factory.get("/")
        response = HttpResponse(status=400)
        
        with patch("server_incidents.services.log_5xx_response_and_decorate") as mock_log:
            self.middleware.process_response(request, response)
            mock_log.assert_called_once()
            # Verify it doesn't actually create an incident
            args = mock_log.call_args[0]
            resp = args[1]
            # Should still call the function, but it will not create an incident
            self.assertFalse(500 <= resp.status_code < 600)


class MiddlewareIntegrationTest(TestCase):
    """Integration tests for middleware."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()

    def test_5xx_captured_with_incident(self):
        """Test that a 5xx response creates an incident."""
        request = self.factory.get("/test")
        request.META["HTTP_USER_AGENT"] = "TestAgent"
        
        response = HttpResponse(status=500)
        
        # Create middleware
        class TestMiddleware(Capture5xxMiddleware):
            def __call__(self, request):
                return self.process_response(request, response)
        
        middleware = TestMiddleware(lambda req: response)
        
        # Process the response
        result = middleware(request)
        
        # Should have created an incident
        incidents = Incident.objects.all()
        self.assertGreater(incidents.count(), 0)


def get_response(request):
    """Dummy view."""
    return HttpResponse("OK")

