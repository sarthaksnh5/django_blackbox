"""
Core services for creating incidents and building error responses.
"""
import random
import traceback
import uuid
from typing import Any

from django.db import IntegrityError
from django.http import JsonResponse
from django.utils import timezone

from django_blackbox.conf import get_conf
from django_blackbox.models import Incident
from django_blackbox.request_id import get_request_id, new_request_id
from django_blackbox.utils import (
    collect_request_meta,
    compute_signature,
    extract_ip_address,
    resolve_user,
    safe_log_to_file,
    should_capture_status_code,
)


def _json_500(message: str, incident_id: str | None, status: int = 500) -> JsonResponse:
    """
    Build a JSON 500 error response.
    
    Args:
        message: The error message to display.
        incident_id: The incident ID to include in the response.
        status: The HTTP status code.
        
    Returns:
        JsonResponse: A JSON error response.
    """
    config = get_conf()
    
    # Determine response status
    response_status = status
    if config.RETURN_400_INSTEAD_OF_500 and status >= 500:
        response_status = 400
    
    # Build response body
    if config.CUSTOM_ERROR_FORMAT:
        # Use custom error format if configured
        body = config.CUSTOM_ERROR_FORMAT.copy()
        # Replace placeholder with incident_id
        for key, value in body.items():
            if isinstance(value, str) and incident_id:
                body[key] = value.replace('<incident_id>', str(incident_id))
            if '<incident_id>' in str(value) and incident_id:
                body[key] = str(value).replace('<incident_id>', str(incident_id))
        # Add incident_id to the body
        if "incident_id" not in body and incident_id:
            body["incident_id"] = str(incident_id)
    else:
        # Default format
        body: dict[str, Any] = {"detail": message}
        
        if config.INCLUDE_INCIDENT_ID_IN_BODY and incident_id:
            body["incident_id"] = str(incident_id)
    
    return JsonResponse(body, status=response_status)


def _should_capture(
    request: Any,
    exception_class: str | None = None,
    http_status: int | None = None,
) -> bool:
    """
    Determine if an incident should be captured based on configuration.
    
    Args:
        request: The Django request object.
        exception_class: The exception class name (if any).
        http_status: The HTTP status code (if any).
        
    Returns:
        bool: True if the incident should be captured.
    """
    config = get_conf()
    
    # Check if enabled
    if not config.ENABLED:
        return False
    
    # Check if path should be ignored
    for pattern in config._compiled_ignore_paths:
        if pattern.search(request.path):
            return False
    
    # Check if exception should be ignored
    if exception_class:
        for ignored in config.IGNORE_EXCEPTIONS:
            if exception_class.startswith(ignored):
                return False
    
    # Check HTTP status (only capture 5xx)
    if http_status is not None and not (500 <= http_status < 600):
        return False
    
    # Check sampling rate
    if random.random() >= config.SAMPLE_RATE:
        return False
    
    return True


def safe_persist_incident(
    meta: dict,
    http_status: int,
    exception_class: str | None,
    exception_message: str | None,
    stacktrace: str | None,
    dedup_hash: str,
) -> Incident:
    """
    Safely persist an incident to the database with fallback logging.
    
    Args:
        meta: Request metadata dictionary.
        http_status: The HTTP status code.
        exception_class: The exception class name (or None).
        exception_message: The exception message (or None).
        stacktrace: The stacktrace (or None).
        dedup_hash: The deduplication hash.
        
    Returns:
        Incident: The created or updated incident.
    """
    config = get_conf()
    
    # Get request ID from meta or generate new one
    request_id_str = meta.get("request_id") or new_request_id()
    try:
        request_id = uuid.UUID(request_id_str)
    except (ValueError, TypeError):
        request_id = uuid.uuid4()
    
    # incident_id is generated inside create_or_increment when creating (to avoid races)
    incident_id = Incident.generate_incident_id()

    # If no stacktrace but we have an exception message that looks like a stacktrace,
    # make sure it's stored in the stacktrace field
    if not stacktrace and exception_message and len(exception_message) > 200 and "Traceback" in exception_message:
        stacktrace = exception_message

    # Prepare defaults for create_or_increment
    defaults = {
        "request_id": request_id,
        "incident_id": incident_id,
        "status": Incident.Status.OPEN,
        "http_status": http_status,
        "method": meta.get("method", "GET"),
        "path": meta.get("path", ""),
        "query_string": meta.get("query_string", ""),
        "user_id": meta.get("user_id"),
        "session_key": meta.get("session_key"),
        "ip_address": meta.get("ip_address"),
        "user_agent": meta.get("user_agent"),
        "headers": meta.get("headers", {}),
        "body_preview": meta.get("body_preview"),
        "content_type": meta.get("content_type"),
        "exception_class": exception_class,
        "exception_message": exception_message,
        "stacktrace": stacktrace,
        "occurred_at": timezone.now(),
        "dedup_hash": dedup_hash,
        "occurrence_count": 1,
    }
    
    try:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                incident, created = Incident.objects.create_or_increment(
                    signature=dedup_hash,
                    defaults=defaults,
                    window_seconds=config.DEDUP_WINDOW_SECONDS,
                )
                return incident
            except IntegrityError as e:
                # Duplicate incident_id (race): retry; manager generates id inside transaction
                if "incident_id" in str(e) and attempt < max_attempts - 1:
                    continue
                raise
    except Exception as e:
        # Fallback logging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to persist incident to database: {e}")
        
        # Log to file
        safe_log_to_file({
            "request_id": str(request_id),
            "incident_id": str(incident_id),
            "path": meta.get("path"),
            "http_status": http_status,
            "exception_class": exception_class,
            "exception_message": exception_message,
            "persist_error": str(e),
        })
        
        # Return a minimal incident-like object
        from types import SimpleNamespace
        incident = SimpleNamespace()
        incident.incident_id = incident_id
        incident.request_id = request_id
        return incident


def log_exception_and_build_response(request: Any, exc: Exception) -> JsonResponse | None:
    """
    Log an exception as an incident and build an appropriate response.
    
    Args:
        request: The Django request object.
        exc: The exception that occurred.
        
    Returns:
        JsonResponse | None: A JSON response if configured, None otherwise.
    """
    config = get_conf()
    
    # Check if we should capture this
    exception_class = f"{exc.__class__.__module__}.{exc.__class__.__name__}"
    if not _should_capture(request, exception_class=exception_class):
        return None
    
    # Collect metadata
    meta = collect_request_meta(request)
    
    # Capture exception details
    exception_message = str(exc) if exc else None
    stacktrace = None
    if config.CAPTURE_STACKTRACE:
        stacktrace = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
    
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
    
    # Mark that we've created an incident for this request
    request._django_blackbox_incident_created = True
    
    # If RETURN_400_INSTEAD_OF_500 is enabled, always return a response
    if config.RETURN_400_INSTEAD_OF_500:
        # Always return JSON response with custom format
        resp = _json_500(
            config.GENERIC_ERROR_MESSAGE, 
            incident.incident_id, 
            status=500
        )
        
        # Add headers
        if config.ADD_REQUEST_ID_HEADER and meta["request_id"]:
            resp["X-Request-ID"] = meta["request_id"]
        if config.ADD_INCIDENT_ID_HEADER:
            resp["X-Incident-ID"] = incident.incident_id
        
        return resp
    
    # Otherwise, check if we should return a JSON response
    if not config.EXPOSE_JSON_ERROR_BODY:
        return None
    
    # Check if JSON is appropriate
    accept = request.META.get("HTTP_ACCEPT", "")
    is_json_request = "application/json" in accept.lower()
    
    if not is_json_request:
        return None
    
    # Build JSON response
    resp = _json_500(config.GENERIC_ERROR_MESSAGE, incident.incident_id, status=500)
    
    # Add headers
    if config.ADD_REQUEST_ID_HEADER and meta["request_id"]:
        resp["X-Request-ID"] = meta["request_id"]
    if config.ADD_INCIDENT_ID_HEADER:
        resp["X-Incident-ID"] = incident.incident_id
    
    return resp


def log_5xx_response_and_decorate(request: Any, response: Any) -> Any:
    """
    Log a 5xx HTTP response and decorate with headers.
    
    Args:
        request: The Django request object.
        response: The HTTP response object.
        
    Returns:
        Any: The response with added headers or custom response if configured.
    """
    config = get_conf()
    
    # Check if enabled
    if not config.ENABLED:
        return response
    
    # Skip if incident was already created
    if hasattr(request, '_django_blackbox_incident_created'):
        return response
    
    # Check status code
    status_code = getattr(response, "status_code", 200)
    
    # Check if this status code should be captured based on configuration
    if not should_capture_status_code(status_code):
        return response
    
    # Check if we should capture this (sample rate, ignore paths, etc.)
    if not _should_capture(request, http_status=status_code):
        return response
    
    # Only capture if explicitly enabled
    if not config.CAPTURE_RESPONSE_5XX:
        # Still add headers
        if config.ADD_REQUEST_ID_HEADER:
            rid = get_request_id()
            if rid:
                response["X-Request-ID"] = rid
        return response
    
    # Collect metadata
    meta = collect_request_meta(request)
    
    # Try to get exception info from request (stored in process_exception)
    exception_class = None
    exception_message = f"HTTP {status_code}"
    stacktrace = None
    original_message = None
    
    # Check if we have stored exception info on the request
    if hasattr(request, '_django_blackbox_exception_info'):
        import traceback
        exc_type, exc_value, exc_tb = request._django_blackbox_exception_info
        if exc_type is not None:
            exception_class = f"{exc_type.__module__}.{exc_type.__name__}"
            exception_message = str(exc_value) if exc_value else f"HTTP {status_code}"
            original_message = exception_message
            if exc_tb is not None:
                stacktrace = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    
    # If no stored exception, try to extract exception details from the response body
    except_type_from_request = None
    if hasattr(request, '_django_blackbox_exception_info'):
        try:
            import sys
            exc_info = sys.exc_info()
            if exc_info[0] is not None:
                except_type_from_request = f"{exc_info[0].__module__}.{exc_info[0].__name__}"
        except:
            pass
    
    try:
        # Try to get the response content
        if hasattr(response, 'data') and isinstance(response.data, dict):
            # DRF Response with data dict
            detail = response.data.get('detail', '')
            if detail and detail != config.GENERIC_ERROR_MESSAGE:
                exception_message = detail
                original_message = detail
            # Check if stacktrace was included in the response
            if 'stacktrace' in response.data:
                stacktrace = response.data['stacktrace']
        elif hasattr(response, 'content'):
            # Try to decode JSON from content
            import json
            try:
                content = response.content.decode('utf-8')
                data = json.loads(content)
                detail = data.get('detail', '')
                if detail and detail != config.GENERIC_ERROR_MESSAGE:
                    exception_message = detail
                    original_message = detail
                # Check for stacktrace in response
                if 'stacktrace' in data:
                    stacktrace = data['stacktrace']
                else:
                    # Try to get any error message from the data
                    for key in ['error', 'error_message', 'message']:
                        if key in data and data[key] and str(data[key]) != config.GENERIC_ERROR_MESSAGE:
                            exception_message = str(data[key])
                            original_message = str(data[key])
                            break
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Not JSON, try as plain text
                if response.content:
                    content = response.content.decode('utf-8', errors='ignore')
                    if len(content) < 1000:  # Only use if reasonable size
                        exception_message = content
                        original_message = content
    except Exception:
        # If extraction fails, use default
        pass
    
    # Try to infer exception class from message if not already set
    if not exception_class:
        # First check if we have it from request
        if except_type_from_request:
            exception_class = except_type_from_request
        elif exception_message:
            # Try to extract the exception type from the message
            if "'" in exception_message and "object has no attribute" in exception_message:
                exception_class = "builtins.AttributeError"
            elif "does not exist" in exception_message:
                exception_class = "django.core.exceptions.ValidationError"
            # Add more patterns as needed
    
    # If we have a stacktrace but no original message, use the stacktrace as the exception message
    if stacktrace and not original_message:
        exception_message = stacktrace
    
    # Compute signature using extracted message
    signature = compute_signature(exception_class, meta["path"], exception_message)
    
    # Persist incident
    incident = safe_persist_incident(
        meta=meta,
        http_status=status_code,
        exception_class=exception_class,
        exception_message=exception_message,
        stacktrace=stacktrace,
        dedup_hash=signature,
    )
    
    # Mark that we've created an incident for this request
    request._django_blackbox_incident_created = True
    
    # If we need to return 400 instead of 500, replace the response
    if config.RETURN_400_INSTEAD_OF_500:
        # Create custom response
        resp = _json_500(
            config.GENERIC_ERROR_MESSAGE,
            incident.incident_id,
            status=500
        )
        # Add headers
        if config.ADD_REQUEST_ID_HEADER and meta["request_id"]:
            resp["X-Request-ID"] = meta["request_id"]
        if config.ADD_INCIDENT_ID_HEADER:
            resp["X-Incident-ID"] = incident.incident_id
        return resp
    
    # Otherwise just add headers
    if config.ADD_REQUEST_ID_HEADER and meta["request_id"]:
        response["X-Request-ID"] = meta["request_id"]
    if config.ADD_INCIDENT_ID_HEADER:
        response["X-Incident-ID"] = incident.incident_id
    
    return response

