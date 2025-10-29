"""
Helper functions for django-blackbox.
"""
import traceback
from typing import Any


def add_stacktrace_to_response(response: Any, exception: Exception) -> None:
    """
    Add stacktrace to a DRF Response object so it can be captured by incident logging.
    
    This is useful when your view catches an exception and returns a Response.
    The stacktrace will be automatically extracted and stored in the incident.
    
    Usage:
        from django_blackbox.helpers import add_stacktrace_to_response
        from rest_framework.response import Response
        
        try:
            # your code
            part.append({...})
        except Exception as e:
            response = Response({"detail": str(e)}, status=500)
            add_stacktrace_to_response(response, e)
            return response
    
    Args:
        response: A DRF Response object
        exception: The exception that was caught
    """
    if hasattr(response, 'data') and isinstance(response.data, dict):
        # Add stacktrace to response data
        tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        response.data['stacktrace'] = tb


def create_error_response(message: str, exception: Exception) -> Any:
    """
    Create a Response with error message and stacktrace already included.
    
    This is a convenience function that creates a 500 response with both
    the error message and stacktrace, ready to be captured by incident logging.
    
    Usage:
        from django_blackbox.helpers import create_error_response
        
        try:
            # your code
            part.append({...})
        except Exception as e:
            return create_error_response(
                f"An error occurred while generating the report: {e}",
                e
            )
    
    Args:
        message: The error message to display
        exception: The exception that was caught
        
    Returns:
        Response: A DRF Response with status 500 containing message and stacktrace
    """
    from rest_framework.response import Response
    
    tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    
    return Response(
        {
            "detail": message,
            "stacktrace": tb
        },
        status=500
    )

