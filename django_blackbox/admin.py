"""
Admin interface for managing server incidents.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from django_blackbox.models import Incident


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

