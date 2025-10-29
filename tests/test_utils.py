"""
Tests for utility functions.
"""
from django.test import RequestFactory, TestCase

from django_blackbox.utils import (
    compute_signature,
    extract_ip_address,
    normalize_message,
    redact_body,
    redact_headers,
)


class RedactionTest(TestCase):
    """Test redaction utilities."""

    def test_redact_headers(self):
        """Test redacting headers."""
        headers = {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
            "X-API-Key": "secret123",
        }
        
        redacted = redact_headers(
            headers,
            ["authorization", "x-api-key"],
            "[REDACTED]",
        )
        
        self.assertEqual(redacted["Authorization"], "[REDACTED]")
        self.assertEqual(redacted["X-API-Key"], "[REDACTED]")
        self.assertEqual(redacted["Content-Type"], "application/json")

    def test_redact_body_dict(self):
        """Test redacting dict body."""
        body = {
            "username": "testuser",
            "password": "secret123",
            "email": "test@example.com",
        }
        
        redacted = redact_body(
            body,
            ["password"],
            "[REDACTED]",
            1024,
            "application/json",
        )
        
        self.assertIn("username", redacted)
        self.assertIn("[REDACTED]", redacted)
        self.assertNotIn("secret123", redacted)

    def test_redact_body_nested(self):
        """Test redacting nested dict structure."""
        body = {
            "user": {
                "name": "Test",
                "password": "secret",
            },
            "token": "abc123",
        }
        
        redacted = redact_body(
            body,
            ["password", "token"],
            "[REDACTED]",
            1024,
            "application/json",
        )
        
        self.assertIn("user", redacted)
        self.assertIn("[REDACTED]", redacted)


class NormalizationTest(TestCase):
    """Test message normalization."""

    def test_normalize_uuid(self):
        """Test UUID normalization."""
        message = "User 123e4567-e89b-12d3-a456-426614174000 not found"
        normalized = normalize_message(message)
        
        self.assertNotIn("123e4567-e89b-12d3-a456-426614174000", normalized)
        self.assertIn("<UUID>", normalized)

    def test_normalize_ip(self):
        """Test IP address normalization."""
        message = "Connection failed to 192.168.1.1"
        normalized = normalize_message(message)
        
        self.assertIn("<IP>", normalized)

    def test_compute_signature(self):
        """Test signature computation."""
        signature1 = compute_signature(
            "ValueError",
            "/test",
            "Something went wrong",
        )
        signature2 = compute_signature(
            "ValueError",
            "/test",
            "Something went wrong",
        )
        
        # Same inputs should yield same signature
        self.assertEqual(signature1, signature2)
        
        # Different message should yield different signature
        signature3 = compute_signature(
            "ValueError",
            "/test",
            "Different error",
        )
        self.assertNotEqual(signature1, signature3)


class IPExtractionTest(TestCase):
    """Test IP address extraction."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()

    def test_extract_from_x_forwarded_for(self):
        """Test extracting IP from X-Forwarded-For."""
        request = self.factory.get(
            "/",
            HTTP_X_FORWARDED_FOR="192.168.1.1, 10.0.0.1",
        )
        
        ip = extract_ip_address(request)
        self.assertEqual(ip, "192.168.1.1")

    def test_extract_from_remote_addr(self):
        """Test extracting IP from REMOTE_ADDR."""
        request = self.factory.get("/")
        request.META["REMOTE_ADDR"] = "192.168.1.1"
        
        ip = extract_ip_address(request)
        self.assertEqual(ip, "192.168.1.1")

