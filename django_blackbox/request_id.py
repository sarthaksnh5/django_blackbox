"""
Context variable management for per-request request IDs.
Each request gets a unique identifier that's exposed via X-Request-ID header.
"""
import uuid
from contextvars import ContextVar
from typing import Any

# Context variable to store the current request ID
_request_id: ContextVar[Any] = ContextVar("django_blackbox_request_id", default=None)


def get_request_id() -> str | None:
    """
    Get the current request ID from the context variable.
    
    Returns:
        str | None: The current request ID, or None if not set.
    """
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    """
    Set the current request ID in the context variable.
    
    Args:
        value: The request ID to set.
    """
    _request_id.set(value)


def new_request_id() -> str:
    """
    Generate a new UUID4 request ID.
    
    Returns:
        str: A new UUID string.
    """
    return str(uuid.uuid4())

