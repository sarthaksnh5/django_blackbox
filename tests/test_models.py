"""
Tests for Incident model.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from django_blackbox.models import Incident


class IncidentModelTest(TestCase):
    """Test Incident model functionality."""

    def setUp(self):
        """Set up test data."""
        import uuid
        self.incident_id = uuid.uuid4()
        self.request_id = uuid.uuid4()

    def test_incident_creation(self):
        """Test creating an incident."""
        incident = Incident.objects.create(
            request_id=self.request_id,
            incident_id=self.incident_id,
            status=Incident.Status.OPEN,
            http_status=500,
            method="GET",
            path="/test",
            dedup_hash="abc123",
        )
        
        self.assertEqual(incident.request_id, self.request_id)
        self.assertEqual(incident.incident_id, self.incident_id)
        self.assertEqual(incident.status, Incident.Status.OPEN)
        self.assertEqual(incident.http_status, 500)
        self.assertEqual(incident.occurrence_count, 1)

    def test_deduplication_within_window(self):
        """Test deduplication within the time window."""
        # Create first incident
        incident1, created1 = Incident.objects.create_or_increment(
            signature="test_signature",
            defaults={
                "request_id": self.request_id,
                "incident_id": self.incident_id,
                "status": Incident.Status.OPEN,
                "http_status": 500,
                "method": "GET",
                "path": "/test",
                "dedup_hash": "test_signature",
            },
            window_seconds=300,
        )
        
        self.assertTrue(created1)
        self.assertEqual(incident1.occurrence_count, 1)
        
        # Create another incident with same signature within window
        import uuid
        incident2, created2 = Incident.objects.create_or_increment(
            signature="test_signature",
            defaults={
                "request_id": uuid.uuid4(),
                "incident_id": uuid.uuid4(),
                "status": Incident.Status.OPEN,
                "http_status": 500,
                "method": "GET",
                "path": "/test",
                "dedup_hash": "test_signature",
            },
            window_seconds=300,
        )
        
        self.assertFalse(created2)
        self.assertEqual(incident2.occurrence_count, 2)
        self.assertEqual(incident1.id, incident2.id)

    def test_no_deduplication_after_window(self):
        """Test that incidents are not deduplicated after time window."""
        # Create incident with old timestamp
        import uuid
        incident = Incident.objects.create(
            request_id=self.request_id,
            incident_id=self.incident_id,
            status=Incident.Status.OPEN,
            http_status=500,
            method="GET",
            path="/test",
            dedup_hash="test_signature",
            occurred_at=timezone.now() - timedelta(seconds=500),
        )
        
        # Try to dedupe within 300 second window
        incident2, created = Incident.objects.create_or_increment(
            signature="test_signature",
            defaults={
                "request_id": uuid.uuid4(),
                "incident_id": uuid.uuid4(),
                "status": Incident.Status.OPEN,
                "http_status": 500,
                "method": "GET",
                "path": "/test",
                "dedup_hash": "test_signature",
            },
            window_seconds=300,
        )
        
        self.assertTrue(created)
        self.assertNotEqual(incident.id, incident2.id)

    def test_status_transition_to_resolved(self):
        """Test that resolved_at is set when status changes to RESOLVED."""
        import uuid
        incident = Incident.objects.create(
            request_id=self.request_id,
            incident_id=self.incident_id,
            status=Incident.Status.OPEN,
            http_status=500,
            method="GET",
            path="/test",
            dedup_hash="abc123",
        )
        
        self.assertIsNone(incident.resolved_at)
        
        # Change to RESOLVED
        incident.status = Incident.Status.RESOLVED
        incident.save()
        
        self.assertIsNotNone(incident.resolved_at)

    def test_string_representation(self):
        """Test string representation of incident."""
        import uuid
        incident = Incident.objects.create(
            request_id=self.request_id,
            incident_id=self.incident_id,
            status=Incident.Status.OPEN,
            http_status=500,
            method="GET",
            path="/test",
            dedup_hash="abc123",
        )
        
        self.assertIn(str(self.incident_id), str(incident))
        self.assertIn("/test", str(incident))
        self.assertIn("OPEN", str(incident))

