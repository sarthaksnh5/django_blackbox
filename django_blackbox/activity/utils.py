"""
Utility functions for activity logging.
"""
import json
from typing import Any

from django.forms.models import model_to_dict


def normalize_instance(instance: Any) -> dict:
    """
    Normalize a model instance or dict to a serializable dict.
    
    Args:
        instance: A Django model instance, dict, or other serializable object.
        
    Returns:
        dict: A JSON-serializable dictionary.
    """
    if instance is None:
        return {}
    
    # If already a dict, return as-is (but ensure it's JSON-serializable)
    if isinstance(instance, dict):
        # Try to serialize to ensure it's valid JSON
        try:
            json.dumps(instance)
            return instance
        except (TypeError, ValueError):
            # If not JSON-serializable, convert values
            return {k: str(v) for k, v in instance.items()}
    
    # If it's a Django model instance, use model_to_dict
    if hasattr(instance, "_meta"):
        try:
            return model_to_dict(instance)
        except Exception:
            # Fallback: convert to string representation
            return {"__str__": str(instance)}
    
    # If it has a 'data' attribute (e.g., DRF serializer), use that
    if hasattr(instance, "data"):
        data = instance.data
        if isinstance(data, dict):
            return data
    
    # Try to convert to dict if it's a simple object
    if hasattr(instance, "__dict__"):
        return {k: str(v) for k, v in instance.__dict__.items()}
    
    # Last resort: convert to string
    return {"__value__": str(instance)}


def compute_diff(instance_before: dict, instance_after: dict) -> dict:
    """
    Compute a diff between two instance states.
    
    Args:
        instance_before: The state before the change.
        instance_after: The state after the change.
        
    Returns:
        dict: A dictionary mapping field names to [old_value, new_value] tuples.
    """
    diff = {}
    
    # Find changed fields
    all_keys = set(instance_before.keys()) | set(instance_after.keys())
    
    for key in all_keys:
        old_val = instance_before.get(key)
        new_val = instance_after.get(key)
        
        # Compare values (handle None and empty dict/list)
        if old_val != new_val:
            diff[key] = [old_val, new_val]
    
    return diff


def set_request_activity_change(
    request: Any,
    *,
    instance_before: Any = None,
    instance_after: Any = None,
    action: str | None = None,
    custom_action: str | None = None,
    custom_payload: dict | None = None,
) -> None:
    """
    Attach instance state change details to the request so ActivityLoggingMiddleware
    can pick it up and store into RequestActivity.
    
    Args:
        request: The Django request object.
        instance_before: Model instance or dict representing state before the change.
        instance_after: Model instance or dict representing state after the change.
        action: High-level operation, e.g. "create", "update", "delete".
        custom_action: Developer-defined semantic label, e.g. "user_profile_updated".
        custom_payload: An arbitrary JSON-serializable dict with extra context.
    """
    # Normalize instances to dicts
    before_dict = normalize_instance(instance_before) if instance_before is not None else {}
    after_dict = normalize_instance(instance_after) if instance_after is not None else {}
    
    # Compute diff
    instance_diff = compute_diff(before_dict, after_dict) if before_dict or after_dict else {}
    
    # Store context on request
    # Use None for action if not provided, so middleware can distinguish between
    # "not set" (None) and "explicitly set to empty" ("")
    request._activity_change_context = {
        "action": action,  # Keep None if not provided, so middleware can use default mapping
        "custom_action": custom_action or "",
        "custom_payload": custom_payload or {},
        "instance_before": before_dict,
        "instance_after": after_dict,
        "instance_diff": instance_diff,
    }

