"""
Serializers for the read-only API.
"""
from rest_framework import serializers

from django_blackbox.models import Incident


class IncidentSerializer(serializers.ModelSerializer):
    """Serializer for Incident model (read-only)."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    formatted_occurred_at = serializers.DateTimeField(
        source="occurred_at",
        read_only=True,
        format="%Y-%m-%d %H:%M:%S %Z",
    )

    class Meta:
        model = Incident
        fields = [
            "incident_id",
            "request_id",
            "status",
            "status_display",
            "http_status",
            "method",
            "path",
            "query_string",
            "user_id",
            "session_key",
            "ip_address",
            "user_agent",
            "headers",
            "body_preview",
            "content_type",
            "exception_class",
            "exception_message",
            "formatted_occurred_at",
            "resolved_at",
            "notes",
            "tags",
            "dedup_hash",
            "occurrence_count",
        ]
        read_only_fields = fields
        # Note: stacktrace excluded by default for size, can be added if needed

