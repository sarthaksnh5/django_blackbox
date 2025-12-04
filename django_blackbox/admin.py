"""
Admin interface for managing server incidents.
"""
import json

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from django_blackbox.models import Incident, RequestActivity


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    """Admin interface for Incident model."""

    list_display = [
        "incident_id",
        "status",
        "http_status",
        "method",
        "path_truncated",
        "occurred_at",
        "occurrence_count",
    ]
    list_filter = [
        "status",
        "http_status",
        ("occurred_at", admin.DateFieldListFilter),
    ]
    search_fields = [
        "path",
        "incident_id",
        "request_id",
        "exception_class",
        "user_id",
        "ip_address",
    ]
    readonly_fields = [
        "id",
        "request_id",
        "incident_id",
        "occurred_at",
        "resolved_at",
        "occurrence_count",
        "dedup_hash",
        "formatted_stacktrace",
        "formatted_headers",
        "formatted_body_preview",
    ]
    fieldsets = (
        (
            "Identifiers",
            {
                "fields": ("incident_id", "request_id", "status", "occurred_at", "resolved_at"),
                "classes": ("wide",),
            },
        ),
        (
            "Request Information",
            {
                "fields": (
                    "http_status",
                    "method",
                    "path",
                    "query_string",
                    "content_type",
                ),
                "classes": ("wide",),
            },
        ),
        (
            "User Information",
            {
                "fields": (
                    "user_id",
                    "session_key",
                    "ip_address",
                    "user_agent",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Exception Details",
            {
                "fields": (
                    "exception_class",
                    "exception_message",
                    "formatted_stacktrace",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Request Data",
            {
                "fields": (
                    "formatted_headers",
                    "formatted_body_preview",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Deduplication",
            {
                "fields": ("dedup_hash", "occurrence_count"),
                "classes": ("collapse",),
            },
        ),
        (
            "Notes",
            {
                "fields": ("notes", "tags"),
            },
        ),
    )
    actions = ["mark_acknowledged", "mark_resolved", "mark_suppressed"]

    def path_truncated(self, obj):
        """Display truncated path."""
        if len(obj.path) > 50:
            return f"{obj.path[:47]}..."
        return obj.path

    path_truncated.short_description = "Path"

    def formatted_stacktrace(self, obj):
        """Display formatted stacktrace with syntax highlighting."""
        if not obj.stacktrace:
            return "-"
        
        # Escape HTML and format as pre block
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto;">{}</pre>',
            mark_safe(obj.stacktrace),
        )
        return html

    formatted_stacktrace.short_description = "Stacktrace"

    def formatted_headers(self, obj):
        """Display formatted headers."""
        if not obj.headers:
            return "-"
        
        formatted = "\n".join(f"{k}: {v}" for k, v in obj.headers.items())
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto;">{}</pre>',
            mark_safe(formatted),
        )
        return html

    formatted_headers.short_description = "Headers"

    def formatted_body_preview(self, obj):
        """Display formatted body preview."""
        if not obj.body_preview:
            return "-"
        
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto; white-space: pre-wrap;">{}</pre>',
            mark_safe(obj.body_preview),
        )
        return html

    formatted_body_preview.short_description = "Body Preview"

    def mark_acknowledged(self, request, queryset):
        """Mark selected incidents as acknowledged."""
        queryset.update(status=Incident.Status.ACKNOWLEDGED)

    mark_acknowledged.short_description = "Mark as Acknowledged"

    def mark_resolved(self, request, queryset):
        """Mark selected incidents as resolved."""
        from django.utils import timezone
        queryset.update(status=Incident.Status.RESOLVED)

    mark_resolved.short_description = "Mark as Resolved"

    def mark_suppressed(self, request, queryset):
        """Mark selected incidents as suppressed."""
        queryset.update(status=Incident.Status.SUPPRESSED)

    mark_suppressed.short_description = "Mark as Suppressed"


@admin.register(RequestActivity)
class RequestActivityAdmin(admin.ModelAdmin):
    """Admin interface for RequestActivity model."""

    list_display = [
        "created_at",
        "method",
        "path_truncated",
        "http_status",
        "user",
        "action",
        "custom_action",
        "request_id",
        "response_time_ms",
    ]
    list_filter = [
        "method",
        "http_status",
        ("created_at", admin.DateFieldListFilter),
        "action",
        "is_authenticated",
    ]
    search_fields = [
        "path",
        "request_id",
        "user__username",
        "user__email",
        "ip_address",
        "custom_action",
        "view_name",
        "route_name",
    ]
    readonly_fields = [
        "id",
        "created_at",
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
        "is_authenticated",
        "ip_address",
        "user_agent",
        "content_type",
        "object_id",
        "formatted_request_headers",
        "formatted_request_body",
        "formatted_response_headers",
        "formatted_response_body",
        "action",
        "formatted_instance_before",
        "formatted_instance_after",
        "formatted_instance_diff",
        "custom_action",
        "formatted_custom_payload",
        "formatted_extra",
    ]
    fieldsets = (
        (
            "Request Information",
            {
                "fields": (
                    "created_at",
                    "method",
                    "path",
                    "full_path",
                    "http_status",
                    "response_time_ms",
                    "view_name",
                    "route_name",
                ),
                "classes": ("wide",),
            },
        ),
        (
            "Correlation",
            {
                "fields": ("request_id", "incident"),
                "classes": ("wide",),
            },
        ),
        (
            "User Information",
            {
                "fields": (
                    "user",
                    "is_authenticated",
                    "ip_address",
                    "user_agent",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Related Object",
            {
                "fields": ("content_type", "object_id"),
                "classes": ("collapse",),
            },
        ),
        (
            "Request Data",
            {
                "fields": (
                    "formatted_request_headers",
                    "formatted_request_body",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Response Data",
            {
                "fields": (
                    "formatted_response_headers",
                    "formatted_response_body",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Instance Change Tracking",
            {
                "fields": (
                    "action",
                    "formatted_instance_before",
                    "formatted_instance_after",
                    "formatted_instance_diff",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Custom Activity",
            {
                "fields": (
                    "custom_action",
                    "formatted_custom_payload",
                    "formatted_extra",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def path_truncated(self, obj):
        """Display truncated path."""
        if len(obj.path) > 50:
            return f"{obj.path[:47]}..."
        return obj.path

    path_truncated.short_description = "Path"

    def formatted_request_headers(self, obj):
        """Display formatted request headers."""
        if not obj.request_headers:
            return "-"
        
        formatted = "\n".join(f"{k}: {v}" for k, v in obj.request_headers.items())
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto;">{}</pre>',
            mark_safe(formatted),
        )
        return html

    formatted_request_headers.short_description = "Request Headers"

    def formatted_request_body(self, obj):
        """Display formatted request body."""
        if not obj.request_body:
            return "-"
        
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto; white-space: pre-wrap;">{}</pre>',
            mark_safe(obj.request_body),
        )
        return html

    formatted_request_body.short_description = "Request Body"

    def formatted_response_headers(self, obj):
        """Display formatted response headers."""
        if not obj.response_headers:
            return "-"
        
        formatted = "\n".join(f"{k}: {v}" for k, v in obj.response_headers.items())
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto;">{}</pre>',
            mark_safe(formatted),
        )
        return html

    formatted_response_headers.short_description = "Response Headers"

    def formatted_response_body(self, obj):
        """Display formatted response body."""
        if not obj.response_body:
            return "-"
        
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto; white-space: pre-wrap;">{}</pre>',
            mark_safe(obj.response_body),
        )
        return html

    formatted_response_body.short_description = "Response Body"

    def formatted_instance_before(self, obj):
        """Display formatted instance before state."""
        if not obj.instance_before:
            return "-"
        
        try:
            formatted = json.dumps(obj.instance_before, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            formatted = str(obj.instance_before)
        
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto;">{}</pre>',
            mark_safe(formatted),
        )
        return html

    formatted_instance_before.short_description = "Instance Before"

    def formatted_instance_after(self, obj):
        """Display formatted instance after state."""
        if not obj.instance_after:
            return "-"
        
        try:
            formatted = json.dumps(obj.instance_after, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            formatted = str(obj.instance_after)
        
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto;">{}</pre>',
            mark_safe(formatted),
        )
        return html

    formatted_instance_after.short_description = "Instance After"

    def formatted_instance_diff(self, obj):
        """Display formatted instance diff."""
        if not obj.instance_diff:
            return "-"
        
        try:
            formatted = json.dumps(obj.instance_diff, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            formatted = str(obj.instance_diff)
        
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto;">{}</pre>',
            mark_safe(formatted),
        )
        return html

    formatted_instance_diff.short_description = "Instance Diff"

    def formatted_custom_payload(self, obj):
        """Display formatted custom payload."""
        if not obj.custom_payload:
            return "-"
        
        try:
            formatted = json.dumps(obj.custom_payload, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            formatted = str(obj.custom_payload)
        
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto;">{}</pre>',
            mark_safe(formatted),
        )
        return html

    formatted_custom_payload.short_description = "Custom Payload"

    def formatted_extra(self, obj):
        """Display formatted extra metadata."""
        if not obj.extra:
            return "-"
        
        try:
            formatted = json.dumps(obj.extra, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            formatted = str(obj.extra)
        
        html = format_html(
            '<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 300px; overflow-y: auto;">{}</pre>',
            mark_safe(formatted),
        )
        return html

    formatted_extra.short_description = "Extra Metadata"

