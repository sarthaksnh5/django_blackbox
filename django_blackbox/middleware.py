"""
Middleware for request ID tracking and 5xx error capture.
"""
import json
import random
import sys
import time
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.http.request import RawPostDataException
from django.utils.deprecation import MiddlewareMixin

from django_blackbox.conf import get_conf
from django_blackbox.models import Incident, RequestActivity
from django_blackbox.request_id import get_request_id, new_request_id, set_request_id
from django_blackbox.services import log_5xx_response_and_decorate, log_exception_and_build_response
from django_blackbox.utils import (
    extract_ip_address,
    extract_user_agent,
    redact_body,
    redact_headers,
    safe_log_to_file,
)


class RequestIDMiddleware(MiddlewareMixin):
    """
    Middleware to track request IDs and add X-Request-ID header to responses.
    
    Sets a unique request ID per request using context variables and optionally
    adds it to the response headers.
    """

    def process_request(self, request):
        """
        Set request ID from incoming header or generate new one.
        
        Args:
            request: The Django request object.
        """
        # Try to get X-Request-ID from incoming request
        incoming_rid = request.META.get("HTTP_X_REQUEST_ID")
        
        # Use incoming ID if present, otherwise generate new one
        if incoming_rid:
            request_id = incoming_rid
        else:
            request_id = new_request_id()
        
        # Set in context
        set_request_id(request_id)
        
        # Also attach to request for easy access
        request.django_blackbox_request_id = request_id

    def process_response(self, request, response):
        """
        Add X-Request-ID header to response.
        
        Args:
            request: The Django request object.
            response: The HTTP response object.
            
        Returns:
            The response with X-Request-ID header added.
        """
        config = get_conf()
        
        if config.ADD_REQUEST_ID_HEADER:
            rid = get_request_id()
            if rid:
                response["X-Request-ID"] = rid
        
        return response


class Capture5xxMiddleware(MiddlewareMixin):
    """
    Middleware to capture 5xx errors and return traceable error responses.
    
    Only captures server-side failures (5xx), never 4xx errors.
    """

    def process_exception(self, request, exception):
        """
        Process exceptions and create incidents.
        
        Args:
            request: The Django request object.
            exception: The exception that occurred.
            
        Returns:
            JsonResponse | None: A JSON response if configured, None to use default handler.
        """
        config = get_conf()
        
        if not config.ENABLED or not config.CAPTURE_EXCEPTIONS:
            return None
        
        # Store exception info in request for later retrieval
        request._django_blackbox_exception_info = sys.exc_info()
        
        # Try to log and build response
        response = log_exception_and_build_response(request, exception)
        
        # If we got a JSON response, return it
        # Otherwise, let Django's default 500 handler deal with it
        # Headers will still be added in process_response
        return response

    def process_response(self, request, response):
        """
        Capture 5xx responses and add incident headers.
        
        Args:
            request: The Django request object.
            response: The HTTP response object.
            
        Returns:
            The response with added headers.
        """
        # Skip if we already handled this in process_exception or DRF handler
        # Check if incident was already created (either via flag or X-Incident-ID header)
        if hasattr(response, '_django_blackbox_incident_created'):
            return response
            
        if hasattr(request, '_django_blackbox_incident_created') and request._django_blackbox_incident_created:
            return response
        
        # Check if X-Incident-ID header is already set (indicating DRF handler created it)
        # This is more reliable than checking the request flag
        try:
            # Works for both Django HttpResponse and DRF Response
            incident_id_header = response.get('X-Incident-ID') if hasattr(response, 'get') else None
            if not incident_id_header and hasattr(response, 'headers'):
                incident_id_header = response.headers.get('X-Incident-ID', '')
        except (AttributeError, TypeError, KeyError):
            incident_id_header = None
            
        if incident_id_header:
            # Mark request so subsequent checks also skip
            request._django_blackbox_incident_created = True
            return response
        
        response = log_5xx_response_and_decorate(request, response)
        return response


class ActivityLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all HTTP request/response activity.
    
    Captures 2xx, 3xx, 4xx, and 5xx responses with rich metadata.
    Should be placed after RequestIDMiddleware but before Capture5xxMiddleware.
    """

    def __init__(self, get_response):
        """Initialize middleware."""
        self.get_response = get_response
        super().__init__(get_response)

    def __call__(self, request):
        """Process request and log activity."""
        config = get_conf()
        
        # Check if activity logging is enabled
        if not config.ACTIVITY_LOG_ENABLED:
            return self.get_response(request)
        
        # Check if path should be ignored
        for pattern in config._compiled_activity_ignore_paths:
            if pattern.search(request.path):
                return self.get_response(request)
        
        # Check sample rate
        if random.random() >= config.ACTIVITY_LOG_SAMPLE_RATE:
            return self.get_response(request)
        
        # Record start time
        start_time = time.monotonic()
        request._activity_start_time = start_time
        
        # Process request
        try:
            response = self.get_response(request)
        except Exception:
            # Even if exception occurs, try to log the activity
            response = None
            raise
        finally:
            # Always log activity, even if exception occurred
            try:
                self._log_activity(request, response, start_time)
            except Exception:
                # Never break the response due to logging errors
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Failed to log request activity")
        
        return response

    def _log_activity(self, request: Any, response: Any, start_time: float) -> None:
        """Log request activity to database."""
        config = get_conf()
        
        # Calculate response time
        response_time_ms = (time.monotonic() - start_time) * 1000
        
        # Get request ID
        request_id = getattr(request, "django_blackbox_request_id", None) or get_request_id() or ""
        
        # Collect basic request info
        method = request.method
        path = request.path
        query_string = request.META.get("QUERY_STRING", "")
        full_path = path
        if query_string:
            full_path = f"{path}?{query_string}"
        
        # Get HTTP status
        http_status = getattr(response, "status_code", 500) if response else 500
        
        # Extract view/route info
        view_name = ""
        route_name = ""
        if hasattr(request, "resolver_match") and request.resolver_match:
            view_name = getattr(request.resolver_match, "view_name", "") or ""
            route_name = getattr(request.resolver_match, "url_name", "") or ""
        
        # Collect headers (with redaction)
        request_headers = {}
        for key, value in request.META.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").title()
                request_headers[header_name] = value
        
        if config.REDACT_SENSITIVE_DATA:
            request_headers = redact_headers(request_headers, config.REDACT_HEADERS, config.REDACT_MASK)
        
        # Collect request body (with redaction and truncation)
        # Build unified request payload including query params and body data
        from django.http import QueryDict
        
        request_payload = {}
        
        # 1. Collect query parameters
        query_params = {}
        try:
            qd = request.GET
            if isinstance(qd, QueryDict) and qd:
                query_params = {
                    k: qd.getlist(k) if len(qd.getlist(k)) > 1 else qd.get(k)
                    for k in qd.keys()
                }
        except Exception:
            query_params = {}
        
        if query_params:
            request_payload["query"] = query_params
        
        # 2. Collect parsed body data (DRF request.data or request.POST)
        body_data = None
        
        # Try DRF request.data first                
        if hasattr(request, "data"):            
            try:
                data_attr = request.data
                # Accept any non-None value (including empty dict/list for POST requests)
                # Empty dict/list still indicates a parsed body was present
                if data_attr is not None:
                    body_data = data_attr
            except Exception as e:                
                pass        
        
        # Fallback to request.POST if no DRF data
        if body_data is None:            
            try:
                post_qd = request.POST
                if isinstance(post_qd, QueryDict) and post_qd:
                    body_data = {
                        k: post_qd.getlist(k) if len(post_qd.getlist(k)) > 1 else post_qd.get(k)
                        for k in post_qd.keys()
                    }
            except Exception:
                pass
        
        # 3. Fallback to raw request.body if no parsed data
        raw_body_text = ""
        if not body_data:
            content_type_raw = request.META.get("CONTENT_TYPE", "")
            content_type = content_type_raw.split(";")[0].strip().lower() if content_type_raw else ""
            
            # Only try to read body for mutating methods
            store_body_for_methods = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
            
            if store_body_for_methods and content_type in config.STORE_BODY_CONTENT_TYPES:
                try:
                    raw_body = request.body
                    if isinstance(raw_body, bytes) and raw_body:
                        truncated = raw_body[:config.MAX_BODY_BYTES]
                        raw_body_text = truncated.decode("utf-8", errors="replace")
                except RawPostDataException:
                    # Body already consumed by DRF/Django; skip logging it
                    raw_body_text = ""
                except Exception:
                    raw_body_text = ""
        
        # 4. Add body data or raw body to payload
        # Include body_data even if it's an empty dict/list (indicates parsed body was present)
        if body_data is not None:
            request_payload["body"] = body_data
        elif raw_body_text:
            request_payload["raw"] = raw_body_text
        
        # 5. Apply redaction if configured
        if config.REDACT_SENSITIVE_DATA and request_payload:
            if "body" in request_payload and isinstance(request_payload["body"], dict):
                redacted_body = request_payload["body"].copy()
                for field in config.REDACT_FIELDS:
                    if field in redacted_body:
                        redacted_body[field] = config.REDACT_MASK
                request_payload["body"] = redacted_body
        
        # 6. Convert to JSON string
        request_body = ""
        if request_payload:
            try:
                request_body_text = json.dumps(request_payload, default=str, separators=(",", ":"), ensure_ascii=False)
                # Truncate if needed
                request_body_bytes = request_body_text.encode("utf-8")
                if len(request_body_bytes) > config.MAX_BODY_BYTES:
                    request_body = request_body_bytes[:config.MAX_BODY_BYTES].decode("utf-8", errors="replace") + "..."
                else:
                    request_body = request_body_text
            except Exception:
                request_body = ""
        
        # Collect response headers
        response_headers = {}
        if response:
            try:
                if hasattr(response, "headers"):
                    # DRF Response (headers is a dict-like object)
                    response_headers = dict(response.headers)
                elif hasattr(response, "_headers"):
                    # Django HttpResponse (older style)
                    response_headers = {k: v for k, v in response._headers.values()}
                else:
                    # Try get method for standard HttpResponse
                    if hasattr(response, "keys"):
                        for key in response.keys():
                            response_headers[key] = response.get(key, "")
            except Exception:
                response_headers = {}
        
        if config.REDACT_SENSITIVE_DATA:
            response_headers = redact_headers(response_headers, config.REDACT_HEADERS, config.REDACT_MASK)
        
        # Collect response body
        # Default to True unless explicitly disabled (changed from False to True)
        store_response_body = getattr(config, "STORE_RESPONSE_BODY", True)
        response_body = ""
        
        if store_response_body and response:
            try:
                # Try DRF Response first (has .data attribute)
                # Check if it's a DRF Response by checking for .data attribute and type
                try:
                    from rest_framework.response import Response as DRFResponse
                except ImportError:
                    DRFResponse = None
                
                is_drf_response = DRFResponse is not None and isinstance(response, DRFResponse)
                has_data_attr = hasattr(response, "data")
                
                if is_drf_response or has_data_attr:
                    try:
                        data = response.data
                        if data is not None:
                            if isinstance(data, (dict, list)):
                                response_body_text = json.dumps(data, default=str, separators=(",", ":"), ensure_ascii=False)
                            else:
                                response_body_text = str(data)
                            
                            # Truncate if needed
                            response_body_bytes = response_body_text.encode("utf-8")
                            if len(response_body_bytes) > config.MAX_RESPONSE_BODY_BYTES:
                                response_body = response_body_bytes[:config.MAX_RESPONSE_BODY_BYTES].decode("utf-8", errors="replace") + "..."
                            else:
                                response_body = response_body_text
                    except (TypeError, ValueError, AttributeError):
                        # Fallback: try to stringify
                        try:
                            response_body = str(response.data)[:config.MAX_RESPONSE_BODY_BYTES]
                        except Exception:
                            response_body = ""
                
                # Fallback: use response.content if DRF data didn't work or not DRF response
                if not response_body and hasattr(response, "content"):
                    try:
                        raw_content = response.content
                        if isinstance(raw_content, bytes) and raw_content:
                            truncated = raw_content[:config.MAX_RESPONSE_BODY_BYTES]
                            response_body = truncated.decode("utf-8", errors="replace")
                    except Exception:
                        response_body = ""
            except Exception:
                # Silently skip if we can't parse response body
                response_body = ""
        
        # Get user info
        user = None
        is_authenticated = False
        if hasattr(request, "user") and request.user.is_authenticated:
            user = request.user
            is_authenticated = True
        
        # Get IP and user agent
        ip_address = extract_ip_address(request)
        user_agent = extract_user_agent(request) or ""
        
        # Link to incident if one was created
        incident = None
        if hasattr(request, "_django_blackbox_incident_created") and request._django_blackbox_incident_created:
            # Try to find the incident by request_id
            # Note: Incident.request_id is UUIDField, so we need to convert string to UUID
            try:
                import uuid
                request_id_uuid = uuid.UUID(request_id) if request_id else None
                if request_id_uuid:
                    incident = Incident.objects.filter(request_id=request_id_uuid).order_by("-occurred_at").first()
            except (ValueError, TypeError, AttributeError):
                # request_id might not be a valid UUID, skip linking
                pass
        
        # Try to determine related object (Generic FK)
        content_type = None
        object_id = ""
        if hasattr(request, "resolver_match") and request.resolver_match:
            try:
                # For DRF ViewSets
                if hasattr(request, "parser_context") and request.parser_context:
                    view = request.parser_context.get("view")
                    if view and hasattr(view, "get_queryset"):
                        try:
                            queryset = view.get_queryset()
                            if queryset and hasattr(queryset, "model"):
                                model = queryset.model
                                lookup_field = getattr(view, "lookup_field", "pk")
                                lookup_url_kwarg = getattr(view, "lookup_url_kwarg", lookup_field)
                                
                                if lookup_url_kwarg in request.resolver_match.kwargs:
                                    lookup_value = request.resolver_match.kwargs[lookup_url_kwarg]
                                    content_type = ContentType.objects.get_for_model(model)
                                    object_id = str(lookup_value)
                        except Exception:
                            pass
                
                # Fallback: try to get from kwargs (for Django CBVs)
                if not content_type and request.resolver_match.kwargs:
                    # Look for common keys like 'pk', 'id'
                    for key in ["pk", "id", "object_id"]:
                        if key in request.resolver_match.kwargs:
                            object_id = str(request.resolver_match.kwargs[key])
                            # Try to infer model from view class
                            if hasattr(request.resolver_match, "func") and hasattr(request.resolver_match.func, "view_class"):
                                view_class = request.resolver_match.func.view_class
                                if hasattr(view_class, "model"):
                                    try:
                                        content_type = ContentType.objects.get_for_model(view_class.model)
                                    except Exception:
                                        pass
                            break
            except Exception:
                # Best-effort, never fail
                pass
        
        # Get activity change context if set by helper/decorator
        activity_ctx = getattr(request, "_activity_change_context", None) or {}
        # Get explicit_action - it may be None (not set), "" (explicitly empty), or a string
        explicit_action = activity_ctx.get("action") if activity_ctx else None
        custom_action = activity_ctx.get("custom_action", "") if activity_ctx else ""
        custom_payload = activity_ctx.get("custom_payload", {}) if activity_ctx else {}
        instance_before = activity_ctx.get("instance_before", {}) if activity_ctx else {}
        instance_after = activity_ctx.get("instance_after", {}) if activity_ctx else {}
        instance_diff = activity_ctx.get("instance_diff", {}) if activity_ctx else {}
        
        # Compute action based on HTTP method if not explicitly set
        method_upper = method.upper() if method else ""
        
        if explicit_action is not None and explicit_action != "":
            # Use explicit action from helper/decorator (non-empty string)
            action = explicit_action
        elif custom_action and (explicit_action is None or explicit_action == ""):
            # If custom_action is set but no explicit action (or explicit action is empty), use "CUSTOM"
            action = "CUSTOM"
        else:
            # Default action mapping based on HTTP method
            if method_upper == "GET":
                action = "VIEW"
            elif method_upper == "POST":
                # POST can be CREATE or UPDATE
                # If we have object_id/content_type (detail view) or instance_before (change tracking),
                # treat it as UPDATE
                has_object_context = bool(object_id)  # object_id is set from URL params
                has_instance_before = bool(instance_before)  # instance_before is a dict from helper
                if has_object_context or has_instance_before:
                    action = "UPDATE"
                else:
                    action = "CREATE"
            elif method_upper in ("PUT", "PATCH"):
                action = "UPDATE"
            elif method_upper == "DELETE":
                action = "DELETE"
            else:
                # For other methods (HEAD, OPTIONS, etc.), use the method name
                action = method_upper or ""
        
        # Create RequestActivity
        try:
            activity = RequestActivity.objects.create(
                method=method,
                path=path,
                full_path=full_path,
                http_status=http_status,
                response_time_ms=response_time_ms,
                view_name=view_name,
                route_name=route_name,
                request_id=request_id,
                incident=incident,
                user=user,
                is_authenticated=is_authenticated,
                ip_address=ip_address,
                user_agent=user_agent,
                content_type=content_type,
                object_id=object_id,
                request_headers=request_headers,
                request_body=request_body,
                response_headers=response_headers,
                response_body=response_body,
                action=action,
                instance_before=instance_before,
                instance_after=instance_after,
                instance_diff=instance_diff,
                custom_action=custom_action,
                custom_payload=custom_payload,
            )
        except Exception as e:
            # Fallback logging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to persist request activity to database: {e}")
            
            # Log to file
            safe_log_to_file({
                "request_id": request_id,
                "method": method,
                "path": path,
                "http_status": http_status,
                "persist_error": str(e),
            })

