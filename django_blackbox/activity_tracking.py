"""
Generic instance change tracking for request activity logging.

Uses Django signals (pre_save/post_save) and contextvars to automatically
track model instance changes during HTTP requests without requiring
any application-specific code.
"""

import contextvars
import logging
from typing import Any, Dict, Optional, Tuple

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.forms.models import model_to_dict

logger = logging.getLogger(__name__)

# Per-request activity context
# Stores: { "app_label.ModelName:pk": {"before": {...}, "after": {...}, "deleted": bool } }
_activity_ctx_var: contextvars.ContextVar[Optional[Dict[str, Dict[str, Any]]]] = contextvars.ContextVar(
    "django_blackbox_activity_context",
    default=None,
)


def start_activity_context() -> None:
    """
    Initialize per-request activity context.
    
    Should be called at the beginning of ActivityLoggingMiddleware.__call__.
    """
    _activity_ctx_var.set({})


def get_activity_context() -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Get the activity context dict for the current context.
    
    Returns None if no context was explicitly started (e.g., outside a request).
    This allows signal receivers to check if they're within a request context.
    """
    return _activity_ctx_var.get()


def _instance_key(instance: Any) -> str:
    """
    Build a unique key for an instance as 'app_label.ModelName:pk'.
    
    Args:
        instance: Django model instance
        
    Returns:
        String key like "myapp.MyModel:123"
    """
    model = type(instance)
    meta = instance._meta
    app_label = meta.app_label
    model_name = meta.model_name
    pk = instance.pk
    
    return f"{app_label}.{model_name}:{pk}"


def _instance_to_dict(instance: Any) -> Dict[str, Any]:
    """
    Convert model instance to a JSON-serializable dict (best-effort).
    
    Uses model_to_dict when possible, falls back to attribute iteration
    for edge cases. All values are sanitized to ensure JSON-serializability.
    
    Args:
        instance: Django model instance
        
    Returns:
        Dictionary representation of the instance (all values JSON-serializable)
    """
    from django_blackbox.utils import sanitize_for_json
    
    if instance is None:
        return {}
    
    try:
        data = model_to_dict(instance)
    except Exception:
        # Fallback: manual attribute extraction
        data: Dict[str, Any] = {}
        try:
            for field in instance._meta.get_fields():
                if field.is_relation and field.many_to_one:
                    # ForeignKey: store the related object's pk
                    try:
                        value = getattr(instance, field.name, None)
                        if value is not None:
                            data[field.name] = getattr(value, "pk", None)
                    except Exception:
                        pass
                elif not field.is_relation:
                    # Regular field
                    try:
                        value = getattr(instance, field.name, None)
                        # Skip callables and private attributes
                        if not callable(value) and not field.name.startswith("_"):
                            data[field.name] = value
                    except Exception:
                        pass
        except Exception:
            # Last resort: try basic attribute access
            for attr in dir(instance):
                if attr.startswith("_"):
                    continue
                try:
                    value = getattr(instance, attr)
                    if callable(value):
                        continue
                    # Avoid huge or unserializable values
                    try:
                        repr(value)
                    except Exception:
                        continue
                    data[attr] = value
                except Exception:
                    pass
    
    # Sanitize all values to ensure JSON-serializability (UUID, datetime, Decimal, etc.)
    return sanitize_for_json(data)


def _compute_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Compute field-wise diff between before and after dicts.
    
    Args:
        before: Dictionary of field values before change
        after: Dictionary of field values after change
        
    Returns:
        Dictionary mapping field names to {"before": value, "after": value}
        for fields that changed
    """
    diff: Dict[str, Dict[str, Any]] = {}
    keys = set(before.keys()) | set(after.keys())
    
    for key in keys:
        b = before.get(key)
        a = after.get(key)
        if b != a:
            diff[key] = {"before": b, "after": a}
    
    return diff


def get_tracked_change_for(
    content_type: Optional[ContentType], object_id: str
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Given a ContentType and object_id, return (before, after, diff) from the per-request context.
    
    Args:
        content_type: ContentType instance for the model
        object_id: Primary key value as string
        
    Returns:
        Tuple of (before_dict, after_dict, diff_dict)
    """
    if not content_type or not object_id:
        return {}, {}, {}
    
    try:
        model = content_type.model_class()
        if model is None:
            return {}, {}, {}
        
        # Build the same key used in signals
        app_label = model._meta.app_label
        model_name = model._meta.model_name
        key = f"{app_label}.{model_name}:{object_id}"
        
        ctx = get_activity_context()
        if ctx is None:
            return {}, {}, {}
        
        payload = ctx.get(key, {})
        
        before = payload.get("before", {}) or {}
        after = payload.get("after", {}) or {}
        diff = _compute_diff(before, after) if (before or after) else {}
        
        return before, after, diff
    except Exception:
        # Best-effort: return empty dicts on any error
        logger.debug("Failed to get tracked change for %s:%s", content_type, object_id, exc_info=True)
        return {}, {}, {}


@receiver(pre_save)
def _blackbox_pre_save(sender, instance, **kwargs):
    """
    Capture 'before' state of any model instance within a request activity context.
    
    Only captures state for existing instances (pk is not None).
    New instances will have empty 'before' state.
    """
    try:
        ctx = get_activity_context()
        if ctx is None:
            # No context (e.g., outside a request); skip silently
            return
    except Exception:
        # No context (e.g., outside a request); skip silently
        return
    
    # Only track if instance has a pk (existing object being updated)
    if instance.pk is None:
        # New object; before state is empty
        return
    
    try:
        key = _instance_key(instance)
        entry = ctx.get(key) or {}
        
        # Only set 'before' once per request (first pre_save)
        if "before" not in entry:
            entry["before"] = _instance_to_dict(instance)
            ctx[key] = entry
    except Exception:
        # Best-effort: silently skip on any error
        logger.debug("Failed to capture pre_save state for %s", instance, exc_info=True)


@receiver(post_save)
def _blackbox_post_save(sender, instance, created, **kwargs):
    """
    Capture 'after' state of any model instance within a request activity context.
    
    Captures state for both new (created=True) and updated (created=False) instances.
    """
    try:
        ctx = get_activity_context()
        if ctx is None:
            # No context (e.g., outside a request); skip silently
            return
    except Exception:
        # No context (e.g., outside a request); skip silently
        return
    
    try:
        key = _instance_key(instance)
        entry = ctx.get(key) or {}
        
        # Always update 'after' state (even if instance was just created)
        entry["after"] = _instance_to_dict(instance)
        ctx[key] = entry
    except Exception:
        # Best-effort: silently skip on any error
        logger.debug("Failed to capture post_save state for %s", instance, exc_info=True)

