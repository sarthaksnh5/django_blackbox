"""
Serializers for the read-only API.
"""
from rest_framework import serializers

from django_blackbox.models import Incident, RequestActivity


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


class RequestActivitySerializer(serializers.ModelSerializer):
    """Serializer for RequestActivity model (read-only)."""

    formatted_created_at = serializers.DateTimeField(
        source="created_at",
        read_only=True,
        format="%Y-%m-%d %H:%M:%S %Z",
    )
    user_username = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    related_object_repr = serializers.SerializerMethodField()

    class Meta:
        model = RequestActivity
        fields = [
            "id",
            "created_at",
            "formatted_created_at",
            "method",
            "path",
            "full_path",
            "http_status",
            "response_time_ms",
            "view_name",
            "route_name",
            "request_id",
            "incident",
            "user",
            "user_username",
            "user_email",
            "is_authenticated",
            "ip_address",
            "user_agent",
            "content_type",
            "object_id",
            "related_object_repr",
            "request_headers",
            "request_body",
            "response_headers",
            "response_body",
            "action",
            "instance_before",
            "instance_after",
            "instance_diff",
            "custom_action",
            "custom_payload",
            "extra",
        ]
        read_only_fields = fields

    def get_related_object_repr(self, obj):
        """Get string representation of related object."""
        if obj.related_object:
            return str(obj.related_object)
        return None

