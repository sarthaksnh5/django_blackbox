"""
Tests for redaction and data privacy features.
"""
from django.test import TestCase

from django_blackbox.utils import redact_body, redact_headers


class RedactionTest(TestCase):
    """Test redaction utilities."""

    def test_redact_nested_json(self):
        """Test redacting nested JSON structures."""
        body = {
            "user": {
                "profile": {
                    "name": "Test User",
                    "email": "test@example.com",
                    "password": "secret123",
                }
            },
            "access_token": "abc123",
            "public_data": "visible",
        }
        
        redacted = redact_body(
            body,
            ["password", "access_token"],
            "[REDACTED]",
            2048,
            "application/json",
        )
        
        # Should be a JSON string
        self.assertIsInstance(redacted, str)
        # Should contain public data
        self.assertIn("public_data", redacted)
        # Should not contain secrets
        self.assertNotIn("secret123", redacted)
        self.assertNotIn("abc123", redacted)
        # Should contain redaction markers
        self.assertIn("[REDACTED]", redacted)

    def test_redact_list(self):
        """Test redacting list structures."""
        body = {
            "users": [
                {"username": "user1", "password": "pass1"},
                {"username": "user2", "password": "pass2"},
            ]
        }
        
        redacted = redact_body(
            body,
            ["password"],
            "[REDACTED]",
            2048,
            "application/json",
        )
        
        # Should not contain passwords
        self.assertNotIn("pass1", redacted)
        self.assertNotIn("pass2", redacted)

    def test_header_case_insensitive(self):
        """Test that header redaction is case-insensitive."""
        headers = {
            "Authorization": "Bearer token",
            "AUTHORIZATION": "Bearer token2",
            "authorization": "Bearer token3",
            "Content-Type": "application/json",
        }
        
        redacted = redact_headers(
            headers,
            ["authorization"],
            "[REDACTED]",
        )
        
        self.assertEqual(redacted["Authorization"], "[REDACTED]")
        self.assertEqual(redacted["AUTHORIZATION"], "[REDACTED]")
        self.assertEqual(redacted["authorization"], "[REDACTED]")
        self.assertEqual(redacted["Content-Type"], "application/json")

    def test_truncation(self):
        """Test that large bodies are truncated."""
        large_body = "a" * 5000
        
        redacted = redact_body(
            large_body,
            [],
            "[REDACTED]",
            max_bytes=100,
            content_type="text/plain",
        )
        
        # Should be truncated
        self.assertLessEqual(len(redacted.encode("utf-8")), 100 + len("..."))

