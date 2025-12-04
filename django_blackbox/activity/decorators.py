"""
Decorators for activity logging.
"""
import functools
from typing import Any, Callable

from django_blackbox.activity.utils import normalize_instance, set_request_activity_change


def log_request_activity_change(
    *,
    action: str | None = None,
    custom_action: str | None = None,
    instance_before_attr: str | None = None,
    instance_after_attr: str | None = None,
    extra_payload_callable: Callable | None = None,
):
    """
    Decorator to capture instance changes for POST/PUT/PATCH/DELETE operations.
    
    Args:
        action: High-level operation type ("create", "update", "delete").
        custom_action: Developer-defined semantic label.
        instance_before_attr: Attribute name on the view or request that contains the 'before' instance.
        instance_after_attr: Attribute name on the view or response that contains the 'after' instance.
        extra_payload_callable: Optional callable(request, response) -> dict for custom_payload.
    
    Usage:
        @log_request_activity_change(action="update", custom_action="user_profile_updated")
        def update(self, request, *args, **kwargs):
            return super().update(request, *args, **kwargs)
    """
    def decorator(view_func_or_method: Callable) -> Callable:
        @functools.wraps(view_func_or_method)
        def wrapper(*args, **kwargs):
            request = None
            view = None
            
            # Determine request and view
            if args:
                # First arg is typically 'self' for class-based views or 'request' for function views
                first_arg = args[0]
                if hasattr(first_arg, "request"):
                    # Class-based view (self.request)
                    view = first_arg
                    request = first_arg.request
                elif isinstance(first_arg, type) or hasattr(first_arg, "META"):
                    # Function-based view (request is first arg)
                    request = first_arg
                else:
                    # Try to find request in kwargs
                    request = kwargs.get("request")
            
            if not request:
                # Fallback: try to get from kwargs
                request = kwargs.get("request")
            
            if not request:
                # Can't proceed without request
                return view_func_or_method(*args, **kwargs)
            
            # Get instance_before if specified
            instance_before = None
            if instance_before_attr:
                if hasattr(view, instance_before_attr):
                    instance_before = getattr(view, instance_before_attr)
                elif hasattr(request, instance_before_attr):
                    instance_before = getattr(request, instance_before_attr)
            else:
                # Default behavior: try to get object before the operation
                # For DRF ViewSets, try get_object()
                if view and hasattr(view, "get_object"):
                    try:
                        instance_before = view.get_object()
                    except Exception:
                        pass
            
            # Call the original view
            response = view_func_or_method(*args, **kwargs)
            
            # Get instance_after if specified
            instance_after = None
            if instance_after_attr:
                if hasattr(view, instance_after_attr):
                    instance_after = getattr(view, instance_after_attr)
                elif hasattr(response, instance_after_attr):
                    instance_after = getattr(response, instance_after_attr)
            else:
                # Default behavior: try to get from serializer or view
                if view:
                    # For DRF ViewSets, try serializer.instance
                    if hasattr(view, "get_serializer"):
                        try:
                            serializer = view.get_serializer()
                            if hasattr(serializer, "instance") and serializer.instance:
                                instance_after = serializer.instance
                        except Exception:
                            pass
                    
                    # Fallback: try get_object() again
                    if not instance_after and hasattr(view, "get_object"):
                        try:
                            instance_after = view.get_object()
                        except Exception:
                            pass
            
            # Get custom payload if callable provided
            custom_payload = {}
            if extra_payload_callable:
                try:
                    custom_payload = extra_payload_callable(request, response) or {}
                except Exception:
                    pass
            
            # Set activity change context
            set_request_activity_change(
                request,
                instance_before=instance_before,
                instance_after=instance_after,
                action=action,
                custom_action=custom_action,
                custom_payload=custom_payload,
            )
            
            return response
        
        return wrapper
    return decorator

