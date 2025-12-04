"""
Data models for server incidents.
"""
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils import timezone

from django_blackbox.conf import get_conf

try:
    from django.contrib.postgres.fields import ArrayField
except ImportError:
    # ArrayField not available (not using Postgres)
    ArrayField = None


class IncidentManager(models.Manager):
    """Custom manager for Incident model with deduplication support."""

    def create_or_increment(
        self,
        signature: str,
        defaults: dict,
        window_seconds: int = 300,
    ) -> tuple["Incident", bool]:
        """
        Create a new incident or increment the count of an existing one.
        
        This method implements deduplication by checking if an incident with
        the same signature occurred within the specified time window.
        
        Args:
            signature: The deduplication hash signature.
            defaults: Dictionary of default values for creating a new incident.
            window_seconds: Time window in seconds to check for duplicate incidents.
            
        Returns:
            tuple: (Incident instance, created: bool)
        """
        with transaction.atomic():
            # Look for existing incident within the time window
            since = timezone.now() - timedelta(seconds=window_seconds)
            
            existing = self.filter(
                dedup_hash=signature,
                occurred_at__gte=since,
                status="OPEN",
            ).select_for_update().first()
            
            if existing:
                # Increment occurrence count and update timestamp
                existing.occurrence_count += 1
                existing.occurred_at = timezone.now()
                # Update some fields if provided in defaults
                for key in ["exception_message", "path", "ip_address"]:
                    if key in defaults and getattr(existing, key, None) != defaults[key]:
                        setattr(existing, key, defaults[key])
                existing.save(update_fields=["occurrence_count", "occurred_at", "exception_message", "path", "ip_address"])
                return existing, False
            else:
                # Create new incident
                incident = self.create(**defaults)
                return incident, True


class Incident(models.Model):
    """
    Model to track server-side 5xx errors with rich metadata.
    
    Only captures 5xx errors, never 4xx.
    """

    class Status(models.TextChoices):
        """Incident status choices."""
        OPEN = "OPEN", "Open"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        RESOLVED = "RESOLVED", "Resolved"
        SUPPRESSED = "SUPPRESSED", "Suppressed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_id = models.UUIDField(help_text="Per-request correlation ID")
    incident_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Public-facing incident ID returned to clients (e.g., INCIDENT-0001)",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    http_status = models.PositiveSmallIntegerField()
    method = models.CharField(max_length=10)
    path = models.TextField(db_index=True)
    query_string = models.TextField(null=True, blank=True)
    user_id = models.TextField(null=True, blank=True, db_index=True)
    session_key = models.CharField(max_length=64, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    user_agent = models.TextField(null=True, blank=True)
    headers = models.JSONField(default=dict)
    body_preview = models.TextField(null=True, blank=True)
    content_type = models.CharField(max_length=255, null=True, blank=True)
    exception_class = models.CharField(max_length=255, null=True, blank=True)
    exception_message = models.TextField(null=True, blank=True)
    stacktrace = models.TextField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    
    # Tags: Use ArrayField if Postgres, otherwise CharField
    tags = (
        ArrayField(
            models.CharField(max_length=100),
            default=list,
            blank=True,
            size=None,
        )
        if ArrayField is not None
        else models.CharField(
            max_length=1024,
            blank=True,
            default="",
        )
    )
    
    dedup_hash = models.CharField(max_length=64, db_index=True)
    occurrence_count = models.IntegerField(default=1)

    objects = IncidentManager()
    
    @classmethod
    def generate_incident_id(cls) -> str:
        """
        Generate a human-readable incident ID in format INCIDENT-XXXX.
        
        Returns:
            str: A sequential incident ID like "INCIDENT-0001"
        """
        try:
            # Get the highest existing incident ID
            last_incident = cls.objects.filter(
                incident_id__startswith='INCIDENT-'
            ).extra(
                select={'num': "CAST(SPLIT_PART(incident_id, '-', 2) AS INTEGER)"}
            ).order_by('-num').first()
            
            if last_incident and last_incident.incident_id.startswith('INCIDENT-'):
                # Extract the number part
                try:
                    num_str = last_incident.incident_id.split('-')[1]
                    next_num = int(num_str) + 1
                except (ValueError, IndexError):
                    next_num = 1
            else:
                next_num = 1
            
            return f"INCIDENT-{next_num:04d}"
        except Exception:
            # Fallback: try simple ordering
            try:
                last = cls.objects.filter(incident_id__startswith='INCIDENT-').order_by('incident_id').last()
                if last:
                    num_str = last.incident_id.split('-')[1]
                    next_num = int(num_str) + 1
                else:
                    next_num = 1
                return f"INCIDENT-{next_num:04d}"
            except Exception:
                return f"INCIDENT-{uuid.uuid4().hex[:4].upper()}"

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["-occurred_at"]),
            models.Index(fields=["dedup_hash"]),
            models.Index(fields=["status", "-occurred_at"]),
        ]
        # Partial index for open incidents (if database supports it)
        constraints = [
            models.CheckConstraint(
                check=models.Q(status__in=["OPEN", "ACKNOWLEDGED", "RESOLVED", "SUPPRESSED"]),
                name="valid_status",
            ),
        ]

    def __str__(self) -> str:
        """String representation."""
        return f"Incident {self.incident_id} ({self.path}) - {self.status}"

    def save(self, *args, **kwargs):
        """Override save to auto-set resolved_at when moving to RESOLVED."""
        if self.status == self.Status.RESOLVED and not self.resolved_at:
            self.resolved_at = timezone.now()
        elif self.status != self.Status.RESOLVED and self.resolved_at:
            # Clear resolved_at if status changes away from RESOLVED
            self.resolved_at = None
        super().save(*args, **kwargs)


class RequestActivity(models.Model):
    """
    Model to track all HTTP request/response activity with rich metadata.
    
    Captures 2xx, 3xx, 4xx, and 5xx responses. Can optionally track
    instance state changes for mutating operations (POST/PUT/PATCH/DELETE).
    """

    id = models.BigAutoField(primary_key=True)
    
    # Core metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    method = models.CharField(max_length=10)
    path = models.TextField()
    full_path = models.TextField(blank=True)  # path + querystring
    http_status = models.IntegerField()
    response_time_ms = models.FloatField(null=True, blank=True)
    
    # View/route resolution
    view_name = models.CharField(max_length=255, blank=True)
    route_name = models.CharField(max_length=255, blank=True)
    
    # Request IDs / Correlation
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    incident = models.ForeignKey(
        "django_blackbox.Incident",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
    )
    
    # User context
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="request_activities",
    )
    is_authenticated = models.BooleanField(default=False)
    
    # Client info
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Related object (Generic FK for detail views)
    content_type = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="request_activities",
    )
    object_id = models.CharField(max_length=255, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")
    
    # Request & response data (JSON/text; redacted/truncated as per settings)
    request_headers = models.JSONField(default=dict, blank=True)
    request_body = models.TextField(blank=True)
    response_headers = models.JSONField(default=dict, blank=True)
    response_body = models.TextField(blank=True)
    
    # Instance state change tracking for POST/PUT/PATCH/DELETE
    # High-level action label, e.g. "create", "update", "delete", "custom"
    action = models.CharField(max_length=64, blank=True)
    
    # JSON snapshots of instance state BEFORE and AFTER the operation
    # (e.g. serializer data or model_to_dict output)
    instance_before = models.JSONField(default=dict, blank=True)
    instance_after = models.JSONField(default=dict, blank=True)
    
    # Optional computed diff between before/after (field -> [old, new])
    instance_diff = models.JSONField(default=dict, blank=True)
    
    # Custom action and payload for developer-defined activities
    custom_action = models.CharField(max_length=128, blank=True)
    custom_payload = models.JSONField(default=dict, blank=True)
    
    # Any extra metadata (e.g. tags, feature flags, etc.)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["http_status"]),
            models.Index(fields=["method", "path"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.method} {self.path} [{self.http_status}] ({self.request_id})"


# Explicit exports for public API
__all__ = [
    "Incident",
    "RequestActivity",
    "IncidentManager",
]

