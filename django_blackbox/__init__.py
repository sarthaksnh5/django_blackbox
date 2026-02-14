"""
Django Black Box - Capture and track 5xx server errors with rich metadata.
"""

__version__ = "0.1.3"

from django_blackbox.exceptions import ServerIncident
from django_blackbox.helpers import add_stacktrace_to_response, create_error_response

# Activity logging imports
try:
    from django_blackbox.activity import log_request_activity_change, set_request_activity_change
    __all__ = [
        "ServerIncident",
        "add_stacktrace_to_response",
        "create_error_response",
        "log_request_activity_change",
        "set_request_activity_change",
    ]
except ImportError:
    __all__ = ["ServerIncident", "add_stacktrace_to_response", "create_error_response"]

