"""
Django Black Box - Capture and track 5xx server errors with rich metadata.
"""

__version__ = "0.1.0"

from django_blackbox.exceptions import ServerIncident
from django_blackbox.helpers import add_stacktrace_to_response, create_error_response

__all__ = ["ServerIncident", "add_stacktrace_to_response", "create_error_response"]

