"""
Django REST Framework exception handler integration.
"""
import logging
import traceback

from rest_framework.views import exception_handler as drf_exception_handler

from django_blackbox.conf import get_conf
from django_blackbox.models import Incident
from django_blackbox.request_id import get_request_id, new_request_id
from django_blackbox.services import safe_persist_incident, _json_500
from django_blackbox.utils import collect_request_meta, compute_signature

logger = logging.getLogger(__name__)


def incident_exception_handler(exc, context):
    """
    DRF exception handler that integrates with server incidents.
    
    This handler:
    - Calls DRF's default handler first
    - If it returns a 4xx response, returns it as-is
    - If it returns a 5xx response, creates an incident and returns it
    - If it returns None (unhandled), creates an Incident and returns JSON error
    
    Args:
        exc: The exception that occurred.
        context: The view context dictionary from DRF.
        
    Returns:
        Response | None: The response to return to the client.
    """
    config = get_conf()
    
    # Get request early
    request = context.get("request")
    
    # Call DRF's default handler first
    response = drf_exception_handler(exc, context)
    
    if response is not None:
        # DRF handled the exception
        status_code = response.status_code
        
        # 4xx responses are returned as-is
        if 400 <= status_code < 500:
            return response
        
        # 5xx responses: create incident and return
        if 500 <= status_code < 600:
            # Skip if already created            
            if hasattr(request, '_django_blackbox_incident_created'):
                return response
                
            # Always create an incident for 5xx responses
            exception_class = f"{exc.__class__.__module__}.{exc.__class__.__name__}"
            if exception_class not in config.IGNORE_EXCEPTIONS:
                meta = collect_request_meta(request)
                exception_message = str(exc) if exc else None
                stacktrace = None
                if config.CAPTURE_STACKTRACE:
                    stacktrace = "".join(
                        traceback.format_exception(type(exc), exc, exc.__traceback__)
                    )
                signature = compute_signature(exception_class, meta["path"], exception_message or "")
                incident = safe_persist_incident(
                    meta=meta,
                    http_status=500,
                    exception_class=exception_class,
                    exception_message=exception_message,
                    stacktrace=stacktrace,
                    dedup_hash=signature,
                )
                # Mark that we've created an incident for this request
                request._django_blackbox_incident_created = True
                
                if config.RETURN_400_INSTEAD_OF_500:
                    # Return custom response
                    resp = _json_500(config.GENERIC_ERROR_MESSAGE, incident.incident_id, status=500)
                    if config.ADD_REQUEST_ID_HEADER and meta["request_id"]:
                        resp["X-Request-ID"] = meta["request_id"]
                    if config.ADD_INCIDENT_ID_HEADER:
                        resp["X-Incident-ID"] = incident.incident_id
                    return resp
                
                # Add incident ID to the original response
                if config.ADD_INCIDENT_ID_HEADER:
                    response["X-Incident-ID"] = incident.incident_id
                if config.ADD_REQUEST_ID_HEADER and meta["request_id"]:
                    response["X-Request-ID"] = meta["request_id"]
            
            return response
    
    # If we get here, DRF didn't handle it (response is None)
    # This means it's an unhandled exception
    
    if not config.ENABLED or not config.CAPTURE_EXCEPTIONS:
        return None
    
    # Get the request from context
    request = context.get("request")
    if not request:
        return None
    
    # Check if we should capture this
    exception_class = f"{exc.__class__.__module__}.{exc.__class__.__name__}"
    if exception_class in config.IGNORE_EXCEPTIONS:
        return None
    
    try:
        # Collect metadata
        meta = collect_request_meta(request)
        
        # Capture exception details
        exception_message = str(exc) if exc else None
        
        # Get stacktrace - always capture for unhandled exceptions
        stacktrace = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ) if exc.__traceback__ else None
        
        # Try to get the __cause__ for additional context
        if hasattr(exc, '__cause__') and exc.__cause__:
            cause_trace = "".join(
                traceback.format_exception(type(exc.__cause__), exc.__cause__, exc.__cause__.__traceback__)
            ) if exc.__cause__.__traceback__ else None
            if cause_trace:
                stacktrace = f"CAUSED BY:\n{str(exc.__cause__)}\n{cause_trace}\n\nORIGINAL EXCEPTION:\n{stacktrace}" if stacktrace else cause_trace
                if not exception_message:
                    exception_message = str(exc)
        
        # Compute signature
        signature = compute_signature(exception_class, meta["path"], exception_message or "")
        
        # Persist incident
        incident = safe_persist_incident(
            meta=meta,
            http_status=500,
            exception_class=exception_class,
            exception_message=exception_message,
            stacktrace=stacktrace,
            dedup_hash=signature,
        )
        
        # Mark that we've created an incident for this request - DO THIS IMMEDIATELY
        request._django_blackbox_incident_created = True
        
        # Return JSON error response (status will be adjusted by _json_500 based on config)
        resp = _json_500(config.GENERIC_ERROR_MESSAGE, incident.incident_id, status=500)
        
        # Add headers
        if config.ADD_REQUEST_ID_HEADER and meta["request_id"]:
            resp["X-Request-ID"] = meta["request_id"]
        if config.ADD_INCIDENT_ID_HEADER:
            resp["X-Incident-ID"] = incident.incident_id
        
        return resp
    except Exception as e:
        # Still set flag to prevent middleware from creating duplicate
        request._django_blackbox_incident_created = True
        # Return None to let Django handle it, but flag is set so middleware won't duplicate
        return None

