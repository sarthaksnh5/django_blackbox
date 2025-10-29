"""
Custom exceptions for django-blackbox.
"""
from rest_framework.exceptions import APIException


class ServerIncident(APIException):
    """
    Exception class that signals a server incident should be created.
    
    This exception is designed to be caught by django-blackbox's exception
    handler and creates a proper incident with stack trace.
    
    Usage:
        from django_blackbox.exceptions import ServerIncident
        
        try:
            # your code
            part.append({...})
        except Exception as e:
            raise ServerIncident(f"An error occurred while generating report: {e}") from e
    """
    
    status_code = 500
    default_detail = "A server error occurred."
    default_code = 'server_error'
    
    def __init__(self, detail=None, code=None):
        """
        Initialize the exception.
        
        Args:
            detail: The error message
            code: Error code (optional)
        """
        if detail is None:
            detail = self.default_detail
        super().__init__(detail, code)

