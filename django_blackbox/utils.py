"""
Utility functions for redaction, hashing, metadata collection, and fallback logging.
"""
import hashlib
import json
import logging
import re
import traceback
from datetime import datetime, timedelta
from ipaddress import ip_address
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.utils import timezone

from django_blackbox.conf import get_conf
from django_blackbox.request_id import get_request_id

logger = logging.getLogger(__name__)
User = get_user_model()


def should_capture_status_code(status_code: int) -> bool:
    """
    Check if a status code should trigger incident capture.
    
    Args:
        status_code: The HTTP status code to check.
        
    Returns:
        bool: True if the status code should trigger incident capture.
    """
    config = get_conf()
    
    if not config.ENABLED:
        return False
    
    # Check if status code matches any configured capture rules
    for rule in config.CAPTURE_STATUS_CODES:
        if isinstance(rule, tuple):
            # Range: (start, end)
            start, end = rule
            if start <= status_code <= end:
                return True
        elif isinstance(rule, int):
            # Specific code
            if status_code == rule:
                return True
    
    return False


def redact_headers(headers: dict[str, Any], keys: list[str], mask: str) -> dict[str, Any]:
    """
    Redact sensitive header values.
    
    Args:
        headers: The headers dict to redact.
        keys: List of header keys to redact (case-insensitive).
        mask: The string to use as replacement.
        
    Returns:
        dict: A new dict with redacted values.
    """
    redacted = {}
    keys_lower = {k.lower() for k in keys}
    
    for key, value in headers.items():
        if key.lower() in keys_lower:
            redacted[key] = mask
        else:
            redacted[key] = value
    
    return redacted


def redact_body(
    payload: bytes | str | dict | Any,
    fields: list[str],
    mask: str,
    max_bytes: int,
    content_type: str | None,
) -> str:
    """
    Redact sensitive fields from request body and truncate.
    
    Args:
        payload: The body content (bytes, str, or dict).
        fields: List of field names to redact.
        mask: The string to use as replacement.
        max_bytes: Maximum bytes to store.
        content_type: The content type of the body.
        
    Returns:
        str: The redacted and truncated body as a string.
    """
    # Handle bytes
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
            return _redact_text_body(text, fields, mask, max_bytes, content_type)
        except UnicodeDecodeError:
            preview = payload[:max_bytes // 4]
            return f"[Binary content: {len(payload)} bytes]"
    
    # Handle string
    if isinstance(payload, str):
        return _redact_text_body(payload, fields, mask, max_bytes, content_type)
    
    # Handle dict (parsed JSON)
    if isinstance(payload, dict):
        return _redact_dict_body(payload, fields, mask, max_bytes)
    
    # Fallback
    text = str(payload)
    return text[:max_bytes] if len(text) <= max_bytes else text[:max_bytes] + "..."


def _redact_text_body(text: str, fields: list[str], mask: str, max_bytes: int, content_type: str | None) -> str:
    """Redact text body based on content type."""
    if content_type and "json" in content_type:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return _redact_dict_body(obj, fields, mask, max_bytes)
        except (json.JSONDecodeError, TypeError):
            pass
    
    text_encoded = text.encode("utf-8")
    if len(text_encoded) <= max_bytes:
        return text
    
    truncated = text_encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + "..."


def _redact_dict_body(data: Any, fields: list[str], mask: str, max_bytes: int) -> str:
    """Recursively redact dict values and return as JSON string."""
    if not isinstance(data, dict):
        return str(data)
    
    redacted = _redact_dict_recursive(data, fields, mask)
    
    try:
        json_str = json.dumps(redacted, separators=(",", ":"))
        if len(json_str.encode("utf-8")) <= max_bytes:
            return json_str
        truncated = json_str.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
        return truncated + "..."
    except (TypeError, ValueError):
        return str(redacted)[:max_bytes]


def _redact_dict_recursive(obj: Any, fields: list[str], mask: str) -> Any:
    """Recursively traverse and redact dictionary values."""
    if isinstance(obj, dict):
        return {
            key: mask if key.lower() in [f.lower() for f in fields] else _redact_dict_recursive(value, fields, mask)
            for key, value in obj.items()
        }
    elif isinstance(obj, list):
        return [_redact_dict_recursive(item, fields, mask) for item in obj]
    else:
        return obj


def normalize_message(message: str) -> str:
    """
    Normalize exception messages by replacing IDs, UUIDs, and numbers with placeholders.
    
    Args:
        message: The exception message.
        
    Returns:
        str: The normalized message.
    """
    # Replace UUIDs with placeholder
    message = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "<UUID>",
        message,
        flags=re.IGNORECASE,
    )
    
    # Replace long numeric IDs (more than 4 digits)
    message = re.sub(r"\b\d{5,}\b", "<ID>", message)
    
    # Replace IP addresses
    try:
        ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        message = re.sub(ip_pattern, "<IP>", message)
    except re.error:
        pass
    
    return message


def compute_signature(exception_class: str | None, path: str, message: str) -> str:
    """
    Compute a deduplication signature for an incident.
    
    Args:
        exception_class: The exception class name (or None).
        path: The request path.
        message: The exception message (or status code message).
        
    Returns:
        str: A SHA256 hex digest of the signature.
    """
    normalized_msg = normalize_message(message)
    signature_str = f"{exception_class or 'HTTP5xx'}|{path}|{normalized_msg}"
    return hashlib.sha256(signature_str.encode("utf-8")).hexdigest()


def extract_ip_address(request: HttpRequest) -> str | None:
    """
    Extract the client IP address from request.
    
    Prioritizes X-Forwarded-For, then X-Real-IP, then REMOTE_ADDR.
    
    Args:
        request: The Django request object.
        
    Returns:
        str | None: The IP address or None.
    """
    # Check X-Forwarded-For first
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        ip = xff.split(",")[0].strip()
        try:
            ip_address(ip)
            return ip
        except ValueError:
            pass
    
    # Check X-Real-IP
    xri = request.META.get("HTTP_X_REAL_IP")
    if xri:
        try:
            ip = ip_address(xri.strip())
            return str(ip)
        except ValueError:
            pass
    
    # Fallback to REMOTE_ADDR
    addr = request.META.get("REMOTE_ADDR")
    if addr:
        try:
            ip = ip_address(addr)
            return str(ip)
        except ValueError:
            pass
    
    return None


def extract_user_agent(request: HttpRequest) -> str | None:
    """
    Extract the User-Agent header.
    
    Args:
        request: The Django request object.
        
    Returns:
        str | None: The User-Agent string or None.
    """
    return request.META.get("HTTP_USER_AGENT")


def resolve_user(request: HttpRequest) -> str | None:
    """
    Resolve a user identifier from the request.
    
    Args:
        request: The Django request object.
        
    Returns:
        str | None: A string representation of the user, or None.
    """
    config = get_conf()
    
    # Try custom callable first
    if config.USER_RESOLUTION_CALLABLE:
        try:
            from django.utils.module_loading import import_string
            func = import_string(config.USER_RESOLUTION_CALLABLE)
            return func(request)
        except Exception as e:
            logger.warning(f"Error calling USER_RESOLUTION_CALLABLE: {e}")
    
    # Default: try to get authenticated user
    if hasattr(request, "user") and request.user.is_authenticated:
        return str(request.user.pk)
    
    return None


def collect_request_meta(request: HttpRequest) -> dict[str, Any]:
    """
    Collect rich metadata from the request.
    Optionally redacts sensitive data based on REDACT_SENSITIVE_DATA setting.
    
    Args:
        request: The Django request object.
        
    Returns:
        dict: A dictionary of request metadata (with optional redaction).
    """
    config = get_conf()
    
    # Collect headers
    headers = {}
    for key, value in request.META.items():
        if key.startswith("HTTP_"):
            header_name = key[5:].replace("_", "-").title()
            headers[header_name] = value
    
    # Apply redaction if configured
    if config.REDACT_SENSITIVE_DATA:
        headers = redact_headers(headers, config.REDACT_HEADERS, config.REDACT_MASK)
    
    # Parse request body if applicable
    body_preview = None
    content_type = request.content_type or request.META.get("CONTENT_TYPE", "")
    
    if hasattr(request, "body") and content_type in config.STORE_BODY_CONTENT_TYPES:
        try:
            body_bytes = request.body
            
            # Apply redaction to body if configured
            if config.REDACT_SENSITIVE_DATA:
                body_preview = redact_body(
                    body_bytes,
                    config.REDACT_FIELDS,
                    config.REDACT_MASK,
                    config.MAX_BODY_BYTES,
                    content_type,
                )
            else:
                # Store original body, just truncate to max bytes
                if len(body_bytes) > config.MAX_BODY_BYTES:
                    body_preview = body_bytes[:config.MAX_BODY_BYTES].decode("utf-8", errors="ignore") + "..."
                else:
                    body_preview = body_bytes.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Failed to parse request body: {e}")
            body_preview = "[Unable to parse body]"
    
    return {
        "request_id": get_request_id(),
        "method": request.method,
        "path": request.path,
        "query_string": request.META.get("QUERY_STRING", ""),
        "user_id": resolve_user(request),
        "session_key": getattr(request, "session", {}).session_key if hasattr(request, "session") else None,
        "ip_address": extract_ip_address(request),
        "user_agent": extract_user_agent(request),
        "headers": headers,
        "body_preview": body_preview,
        "content_type": content_type,
    }


def safe_log_to_file(data: dict[str, Any]) -> None:
    """
    Log incident data to a fallback JSONL file if database write fails.
    
    Args:
        data: The incident data to log.
    """
    config = get_conf()
    if not config.FALLBACK_FILE_LOG:
        return
    
    try:
        log_entry = {
            "timestamp": timezone.now().isoformat(),
            **data,
        }
        
        with open(config.FALLBACK_FILE_PATH, "a") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write to fallback log file: {e}")
