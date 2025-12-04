"""
Tests for activity logging feature.
"""
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, TestCase

from django_blackbox.activity.decorators import log_request_activity_change
from django_blackbox.activity.utils import (
    compute_diff,
    normalize_instance,
    set_request_activity_change,
)
from django_blackbox.conf import Config, reset_config
from django_blackbox.middleware import ActivityLoggingMiddleware, RequestIDMiddleware
from django_blackbox.models import Incident, RequestActivity

User = get_user_model()


class ActivityUtilsTest(TestCase):
    """Test activity utility functions."""

    def test_normalize_instance_dict(self):
        """Test normalizing a dict."""
        data = {"name": "test", "value": 123}
        result = normalize_instance(data)
        self.assertEqual(result, data)

    def test_normalize_instance_model(self):
        """Test normalizing a model instance."""
        user = User.objects.create_user(username="testuser", email="test@example.com")
        result = normalize_instance(user)
        self.assertIn("username", result)
        self.assertEqual(result["username"], "testuser")

    def test_compute_diff(self):
        """Test computing diff between two states."""
        before = {"name": "old", "value": 1}
        after = {"name": "new", "value": 1, "new_field": "added"}
        diff = compute_diff(before, after)
        self.assertIn("name", diff)
        self.assertEqual(diff["name"], ["old", "new"])
        self.assertIn("new_field", diff)
        self.assertEqual(diff["new_field"], [None, "added"])

    def test_set_request_activity_change(self):
        """Test setting activity change context on request."""
        factory = RequestFactory()
        request = factory.get("/")
        
        set_request_activity_change(
            request,
            instance_before={"name": "old"},
            instance_after={"name": "new"},
            action="update",
            custom_action="user_updated",
            custom_payload={"extra": "data"},
        )
        
        self.assertTrue(hasattr(request, "_activity_change_context"))
        ctx = request._activity_change_context
        self.assertEqual(ctx["action"], "update")
        self.assertEqual(ctx["custom_action"], "user_updated")
        self.assertEqual(ctx["custom_payload"], {"extra": "data"})
        self.assertIn("instance_before", ctx)
        self.assertIn("instance_after", ctx)
        self.assertIn("instance_diff", ctx)


class ActivityLoggingMiddlewareTest(TestCase):
    """Test ActivityLoggingMiddleware."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        reset_config()

    def get_middleware(self):
        """Get middleware instance."""
        def get_response(request):
            return HttpResponse("OK", status=200)
        return ActivityLoggingMiddleware(get_response)

    def test_simple_get_request_logged(self):
        """Test that a simple GET request creates a RequestActivity."""
        request = self.factory.get("/test")
        
        # Add RequestIDMiddleware first
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        middleware = self.get_middleware()
        response = middleware(request)
        
        activities = RequestActivity.objects.all()
        self.assertEqual(activities.count(), 1)
        
        activity = activities.first()
        self.assertEqual(activity.method, "GET")
        self.assertEqual(activity.path, "/test")
        self.assertEqual(activity.http_status, 200)
        self.assertIsNotNone(activity.request_id)
        self.assertFalse(activity.is_authenticated)
        self.assertIsNone(activity.user)

    def test_authenticated_request_logged(self):
        """Test that an authenticated request logs user info."""
        user = User.objects.create_user(username="testuser", email="test@example.com")
        request = self.factory.get("/test")
        request.user = user
        
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        middleware = self.get_middleware()
        response = middleware(request)
        
        activities = RequestActivity.objects.all()
        self.assertEqual(activities.count(), 1)
        
        activity = activities.first()
        self.assertEqual(activity.user, user)
        self.assertTrue(activity.is_authenticated)

    def test_all_status_codes_logged(self):
        """Test that all status codes (2xx, 3xx, 4xx, 5xx) are logged."""
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(self.factory.get("/"))
        
        for status in [200, 301, 404, 500]:
            request = self.factory.get(f"/test-{status}")
            RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
            
            def get_response(req):
                return HttpResponse(status=status)
            
            middleware = ActivityLoggingMiddleware(get_response)
            middleware(request)
        
        activities = RequestActivity.objects.filter(path__startswith="/test-")
        self.assertEqual(activities.count(), 4)
        
        statuses = set(activities.values_list("http_status", flat=True))
        self.assertEqual(statuses, {200, 301, 404, 500})

    def test_activity_logging_disabled(self):
        """Test that no activity is logged when disabled."""
        with patch("django_blackbox.conf.get_conf") as mock_conf:
            config = Config()
            config.ACTIVITY_LOG_ENABLED = False
            mock_conf.return_value = config
            
            request = self.factory.get("/test")
            RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
            
            middleware = self.get_middleware()
            middleware(request)
            
            activities = RequestActivity.objects.all()
            self.assertEqual(activities.count(), 0)

    def test_ignore_paths(self):
        """Test that ignored paths are not logged."""
        with patch("django_blackbox.conf.get_conf") as mock_conf:
            config = Config()
            config.ACTIVITY_LOG_ENABLED = True
            config.ACTIVITY_LOG_IGNORE_PATHS = [r"^/health/", r"^/metrics"]
            config._compiled_activity_ignore_paths = [
                __import__("re").compile(p) for p in config.ACTIVITY_LOG_IGNORE_PATHS
            ]
            mock_conf.return_value = config
            
            request = self.factory.get("/health/check")
            RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
            
            middleware = self.get_middleware()
            middleware(request)
            
            activities = RequestActivity.objects.all()
            self.assertEqual(activities.count(), 0)
            
            # Non-ignored path should be logged
            request2 = self.factory.get("/api/users")
            RequestIDMiddleware(lambda req: HttpResponse()).process_request(request2)
            middleware(request2)
            
            activities = RequestActivity.objects.all()
            self.assertEqual(activities.count(), 1)

    def test_sample_rate(self):
        """Test that sample rate works correctly."""
        with patch("django_blackbox.conf.get_conf") as mock_conf:
            config = Config()
            config.ACTIVITY_LOG_ENABLED = True
            config.ACTIVITY_LOG_SAMPLE_RATE = 0.0  # Never log
            mock_conf.return_value = config
            
            request = self.factory.get("/test")
            RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
            
            middleware = self.get_middleware()
            middleware(request)
            
            activities = RequestActivity.objects.all()
            self.assertEqual(activities.count(), 0)

    def test_response_time_calculated(self):
        """Test that response time is calculated."""
        import time
        
        request = self.factory.get("/test")
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        def get_response(req):
            time.sleep(0.01)  # Small delay
            return HttpResponse()
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        self.assertIsNotNone(activity.response_time_ms)
        self.assertGreater(activity.response_time_ms, 0)

    def test_linked_to_incident(self):
        """Test that activity is linked to incident when incident is created."""
        request = self.factory.get("/test")
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        request_id = request.django_blackbox_request_id
        
        # Create an incident
        incident = Incident.objects.create(
            request_id=request_id,
            incident_id="INCIDENT-0001",
            http_status=500,
            method="GET",
            path="/test",
            dedup_hash="test_hash",
        )
        
        request._django_blackbox_incident_created = True
        
        def get_response(req):
            return HttpResponse(status=500)
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        self.assertEqual(activity.incident, incident)

    def test_request_response_data_captured(self):
        """Test that request and response data is captured."""
        request = self.factory.post(
            "/test",
            data=json.dumps({"name": "test"}),
            content_type="application/json",
        )
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        def get_response(req):
            resp = JsonResponse({"status": "ok"})
            return resp
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        self.assertIn("request_headers", activity.request_headers)
        # Request body should be captured (may be redacted)
        self.assertIsNotNone(activity.request_body)

    def test_instance_change_tracking(self):
        """Test that instance change tracking works."""
        request = self.factory.post("/test")
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        set_request_activity_change(
            request,
            instance_before={"id": 1, "name": "old"},
            instance_after={"id": 1, "name": "new"},
            action="update",
            custom_action="user_profile_updated",
        )
        
        def get_response(req):
            return HttpResponse()
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        self.assertEqual(activity.action, "update")
        self.assertEqual(activity.custom_action, "user_profile_updated")
        self.assertIn("name", activity.instance_before)
        self.assertIn("name", activity.instance_after)
        self.assertIn("name", activity.instance_diff)
        self.assertEqual(activity.instance_diff["name"], ["old", "new"])

    def test_error_handling_does_not_break_response(self):
        """Test that logging errors don't break the response."""
        request = self.factory.get("/test")
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        # Mock database error
        with patch("django_blackbox.models.RequestActivity.objects.create") as mock_create:
            mock_create.side_effect = Exception("Database error")
            
            def get_response(req):
                return HttpResponse("OK")
            
            middleware = ActivityLoggingMiddleware(get_response)
            response = middleware(request)
            
            # Response should still be returned
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"OK")


class ActivityDecoratorTest(TestCase):
    """Test activity logging decorator."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        reset_config()

    def test_decorator_on_function_view(self):
        """Test decorator on function-based view."""
        @log_request_activity_change(action="create", custom_action="user_created")
        def create_user(request):
            return HttpResponse()
        
        request = self.factory.post("/users")
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        # Need to wrap in middleware to actually log
        def get_response(req):
            return create_user(req)
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        self.assertEqual(activity.action, "create")
        self.assertEqual(activity.custom_action, "user_created")

    def test_decorator_with_instance_tracking(self):
        """Test decorator with instance tracking."""
        user = User.objects.create_user(username="test", email="test@example.com")
        
        class TestView:
            def __init__(self):
                self.request = None
                self._instance_before = user
            
            @log_request_activity_change(
                action="update",
                instance_before_attr="_instance_before",
            )
            def update(self, request):
                self.request = request
                # Simulate update
                user.username = "updated"
                user.save()
                return HttpResponse()
        
        view = TestView()
        request = self.factory.post("/users/1")
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        def get_response(req):
            return view.update(req)
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        self.assertEqual(activity.action, "update")
        # Instance before should be captured
        self.assertIn("username", activity.instance_before)

    def test_request_body_includes_query_params(self):
        """Test that request body includes query parameters."""
        request = self.factory.post(
            "/v1/department/complaint/1431a8e4-2885-4c08-ab9d-5ced0caa7543/accept/?department_id=d8d13ee6-a076-405e-a885-16ce26ab0093",
            data=json.dumps({"foo": "bar"}),
            content_type="application/json",
        )
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        def get_response(req):
            return JsonResponse({"detail": "Invalid department"}, status=400)
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        # Request body should include query params
        self.assertIn("department_id", activity.request_body)
        # Request body should include body data if present
        self.assertIn("foo", activity.request_body)

    def test_response_body_logged(self):
        """Test that response body is logged."""
        request = self.factory.post("/test")
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        def get_response(req):
            return JsonResponse({"detail": "Invalid department"}, status=400)
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        # Response body should contain the error detail
        self.assertIn("Invalid department", activity.response_body)
        self.assertIn("detail", activity.response_body)

    def test_request_body_with_empty_data(self):
        """Test that request body is logged even when request.data is empty dict."""
        request = self.factory.post(
            "/test?param=value",
            data=json.dumps({}),
            content_type="application/json",
        )
        RequestIDMiddleware(lambda req: HttpResponse()).process_request(request)
        
        def get_response(req):
            return JsonResponse({"status": "ok"})
        
        middleware = ActivityLoggingMiddleware(get_response)
        middleware(request)
        
        activity = RequestActivity.objects.first()
        # Request body should include query params
        self.assertIn("param", activity.request_body)
        # Request body should include body (even if empty dict)
        self.assertIn("body", activity.request_body)

