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
    sanitize_for_json,
)


class BodyCaptureMiddleware(MiddlewareMixin):
    """
    Middleware that safely caches the raw request body once, at the very beginning
    of the request lifecycle, so that later middlewares (like ActivityLoggingMiddleware)
    can use it without triggering RawPostDataException.
    
    NOTE: This middleware MUST be placed near the top of MIDDLEWARE, before DRF,
    CSRF, and any middleware that may read request.POST or request.body.
    
    Correct MIDDLEWARE order:
        MIDDLEWARE = [
            # ... security, sessions, etc. ...
            "django_blackbox.middleware.BodyCaptureMiddleware",       # <== Early, before DRF/CSRF
            "django_blackbox.middleware.RequestIDMiddleware",
            "django_blackbox.middleware.ActivityLoggingMiddleware",
            "django_blackbox.middleware.Capture5xxMiddleware",
            # ... DRF, authentication, etc. ...
        ]
    """

    def __init__(self, get_response):
        """Initialize middleware."""
        self.get_response = get_response
        super().__init__(get_response)

    def __call__(self, request):
        """
        Cache the raw request body for mutating methods.
        
        This reads request.body once at the very beginning, which:
        - Populates Django's internal _body cache
        - Allows DRF/CSRF to read it later without issues
        - Stores a copy in request._django_blackbox_raw_body for our logging
        """
        # Only cache for mutating methods; safe no-op for others
        raw_body = None
        try:
            if request.method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
                # Accessing request.body here populates request._body and caches the stream.
                # Django will then reuse this cached body for request.POST / DRF parsing.
                raw_body = request.body
        except RawPostDataException:
            # Body was already read by an even earlier middleware; cannot recover
            raw_body = None
        except Exception:
            # Any other error; safe to ignore
            raw_body = None
        
        # Store cached raw body for downstream use
        request._django_blackbox_raw_body = raw_body
        
        response = self.get_response(request)
        return response


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
        from django_blackbox.activity_tracking import start_activity_context
        
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
        
        # NEW: start per-request activity tracking context
        # This initializes the contextvars context that signal receivers will use
        start_activity_context()
        
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
        
        response_time_ms = self._get_response_time_ms(start_time)
        request_id = self._get_request_id(request)
        method, path, full_path, http_status = self._collect_basic_request_info(request, response)
        view_name, route_name = self._resolve_view_info(request)
        request_headers = self._collect_request_headers(request, config)
        request_body = self._build_request_body(request, method, config)
        response_headers = self._collect_response_headers(response, config)
        response_body = self._build_response_body(response, config)
        user, is_authenticated = self._resolve_user(request)
        ip_address = extract_ip_address(request)
        user_agent = extract_user_agent(request) or ""
        incident = self._resolve_incident(request, request_id)
        content_type, object_id = self._resolve_related_object(request)
        
        # Get manual activity context (if app code explicitly set it)
        activity_ctx = getattr(request, "_activity_change_context", None) or {}
        explicit_action = activity_ctx.get("action")
        custom_action = activity_ctx.get("custom_action", "")
        custom_payload = activity_ctx.get("custom_payload", {})
        instance_before = activity_ctx.get("instance_before", {})
        instance_after = activity_ctx.get("instance_after", {})
        instance_diff = activity_ctx.get("instance_diff", {})
        
        # NEW: overlay automatic tracked changes from signals
        # This gets instance_before/after/diff from pre_save/post_save signals
        from django_blackbox.activity_tracking import get_tracked_change_for
        tracked_before, tracked_after, tracked_diff = get_tracked_change_for(content_type, object_id)
        
        # If manual context didn't set them, use tracked values from signals
        if not instance_before and tracked_before:
            instance_before = tracked_before
        if not instance_after and tracked_after:
            instance_after = tracked_after
        if not instance_diff and tracked_diff:
            instance_diff = tracked_diff
        
        # Resolve action and finalize change context
        action, instance_before, instance_after, instance_diff, custom_action, custom_payload = \
            self._resolve_action_and_change_context(
                method,
                object_id,
                {
                    "action": explicit_action,
                    "custom_action": custom_action,
                    "custom_payload": custom_payload,
                    "instance_before": instance_before,
                    "instance_after": instance_after,
                    "instance_diff": instance_diff,
                },
            )
        
        self._create_request_activity(
            method, path, full_path,
            http_status, response_time_ms, view_name, route_name,
            request_id, incident,
            user, is_authenticated, ip_address, user_agent,
            content_type, object_id,
            request_headers, request_body,
            response_headers, response_body,
            action, instance_before, instance_after, instance_diff,
            custom_action, custom_payload,
            config,
        )
    
    def _get_response_time_ms(self, start_time: float) -> float:
        """Calculate response time in milliseconds."""
        return (time.monotonic() - start_time) * 1000
    
    def _get_request_id(self, request: Any) -> str:
        """Get request ID from request object or context."""
        return getattr(request, "django_blackbox_request_id", None) or get_request_id() or ""
    
    def _collect_basic_request_info(self, request: Any, response: Any) -> tuple[str, str, str, int]:
        """Collect basic request information."""
        method = request.method
        path = request.path
        query_string = request.META.get("QUERY_STRING", "")
        full_path = path
        if query_string:
            full_path = f"{path}?{query_string}"
        http_status = getattr(response, "status_code", 500) if response else 500
        return method, path, full_path, http_status
    
    def _resolve_view_info(self, request: Any) -> tuple[str, str]:
        """Resolve view name and route name from request."""
        view_name = ""
        route_name = ""
        if hasattr(request, "resolver_match") and request.resolver_match:
            view_name = getattr(request.resolver_match, "view_name", "") or ""
            route_name = getattr(request.resolver_match, "url_name", "") or ""
        return view_name, route_name
    
    def _collect_request_headers(self, request: Any, config: Any) -> dict:
        """Collect and redact request headers."""
        request_headers = {}
        for key, value in request.META.items():
            if key.startswith("HTTP_"):
                header_name = key[5:].replace("_", "-").title()
                request_headers[header_name] = value
        
        if config.REDACT_SENSITIVE_DATA:
            request_headers = redact_headers(request_headers, config.REDACT_HEADERS, config.REDACT_MASK)
        
        return request_headers
    
    def _build_request_body(self, request: Any, method: str, config: Any) -> str:
        """Build unified request body payload including query params and body data."""
        import logging
        from django.http import QueryDict
        
        logger = logging.getLogger(__name__)
        
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
                if data_attr is not None:
                    body_data = data_attr
            except Exception:
                body_data = None
        
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
        
        # 3. Use cached raw body from BodyCaptureMiddleware, NEVER call request.body here
        content_type_raw = request.META.get("CONTENT_TYPE", "") or ""
        content_type = content_type_raw.split(";")[0].strip().lower()
        store_body_for_methods = method.upper() in ("POST", "PUT", "PATCH", "DELETE")
        
        # Ensure application/json is always allowed
        store_body_types = set(config.STORE_BODY_CONTENT_TYPES)
        if "application/json" not in store_body_types:
            store_body_types.add("application/json")
        
        # Debug logging
        logger.debug(
            "Blackbox body debug: method=%s content_type=%s has_data_attr=%s",
            method, content_type, hasattr(request, "data"),
        )
        logger.debug(
            "Blackbox body debug: GET=%s POST=%s body_data=%s",
            dict(request.GET), dict(request.POST), body_data is not None,
        )
        raw_body_text = ""
        raw_body_cached = getattr(request, "_django_blackbox_raw_body", None)
        
        logger.debug(
            "Blackbox body debug: method=%s content_type=%s has_data_attr=%s raw_body_cached=%s",
            method, content_type, hasattr(request, "data"), raw_body_cached is not None,
        )
        
        # Try to use cached raw body if:
        # 1. We don't have parsed body data yet
        # 2. It's a mutating method
        # 3. We have a cached raw body
        # 4. Content-type is in allowed types OR it's JSON (always allow JSON)
        should_use_raw = (
            body_data is None and
            store_body_for_methods and
            raw_body_cached is not None and
            (content_type in store_body_types or "application/json" in content_type)
        )
        
        if should_use_raw and isinstance(raw_body_cached, bytes) and raw_body_cached:
            try:
                # Debug: log raw body preview
                logger.debug("Blackbox body raw cached preview: %r", raw_body_cached[:256])
            except Exception:
                pass
            
            # Try JSON first if content-type suggests it
            if "application/json" in content_type:
                try:
                    body_data = json.loads(raw_body_cached.decode("utf-8"))
                    logger.debug("Blackbox body: Successfully parsed cached raw body as JSON")
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    # Not valid JSON; fall back to raw text
                    logger.debug("Blackbox body: JSON parse failed on cached body: %s", e)
                    truncated = raw_body_cached[:config.MAX_BODY_BYTES]
                    raw_body_text = truncated.decode("utf-8", errors="replace")
            else:
                # Not JSON content-type, store as raw text
                truncated = raw_body_cached[:config.MAX_BODY_BYTES]
                raw_body_text = truncated.decode("utf-8", errors="replace")
        
        # 4. Add body data or raw body to payload
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
        if not request_payload:
            return ""
        
        try:
            text = json.dumps(request_payload, default=str, separators=(",", ":"), ensure_ascii=False)
            data_bytes = text.encode("utf-8")
            if len(data_bytes) > config.MAX_BODY_BYTES:
                return data_bytes[:config.MAX_BODY_BYTES].decode("utf-8", errors="replace") + "..."
            return text
        except Exception as e:
            logger.debug("Blackbox body: Exception serializing payload: %s", e)
            return ""
    
    def _collect_response_headers(self, response: Any, config: Any) -> dict:
        """Collect and redact response headers."""
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
        
        return response_headers
    
    def _build_response_body(self, response: Any, config: Any) -> str:
        """Build response body string."""
        store_response_body = getattr(config, "STORE_RESPONSE_BODY", True)
        response_body = ""
        
        if store_response_body and response:
            try:
                # Try DRF Response first
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
                
                # Fallback: use response.content if DRF data didn't work
                if not response_body and hasattr(response, "content"):
                    try:
                        raw_content = response.content
                        if isinstance(raw_content, bytes) and raw_content:
                            truncated = raw_content[:config.MAX_RESPONSE_BODY_BYTES]
                            response_body = truncated.decode("utf-8", errors="replace")
                    except Exception:
                        response_body = ""
            except Exception:
                response_body = ""
        
        return response_body
    
    def _resolve_user(self, request: Any) -> tuple[Any, bool]:
        """Resolve user from request."""
        user = None
        is_authenticated = False
        if hasattr(request, "user") and request.user.is_authenticated:
            user = request.user
            is_authenticated = True
        return user, is_authenticated
    
    def _resolve_incident(self, request: Any, request_id: str) -> Any:
        """Resolve linked incident if one was created."""
        incident = None
        if hasattr(request, "_django_blackbox_incident_created") and request._django_blackbox_incident_created:
            try:
                import uuid
                request_id_uuid = uuid.UUID(request_id) if request_id else None
                if request_id_uuid:
                    incident = Incident.objects.filter(request_id=request_id_uuid).order_by("-occurred_at").first()
            except (ValueError, TypeError, AttributeError):
                pass
        return incident
    
    def _resolve_related_object(self, request: Any) -> tuple[Any, str]:
        """
        Resolve related object (Generic FK) from request.
        
        Uses resolver_match + DRF's router semantics to find the view class and view instance,
        then resolves the model and object_id from URL kwargs.
        
        Returns:
            (content_type, object_id)
        """
        import logging
        
        logger = logging.getLogger(__name__)
        
        content_type = None
        object_id = ""
        
        match = getattr(request, "resolver_match", None)
        if not match:
            return content_type, object_id
        
        # Debug (keep it for now)
        logger.debug(
            "Blackbox related object: path=%s view_name=%s func=%r kwargs=%r",
            getattr(request, "path", ""),
            getattr(match, "view_name", ""),
            getattr(match, "func", None),
            getattr(match, "kwargs", {}),
        )
        
        try:
            # 1. Resolve view_class
            func = match.func
            view_class = None
            
            if hasattr(func, "cls"):
                # DRF ViewSet registered via router
                view_class = func.cls
            elif hasattr(func, "view_class"):
                # Django CBV
                view_class = func.view_class
            
            # 2. Resolve view_instance (DRF request)
            view_instance = None
            if hasattr(request, "parser_context") and request.parser_context:
                view_instance = request.parser_context.get("view")
            
            # 3. Resolve model
            model = None
            
            # 3a. DRF view instance queryset / serializer
            if view_instance is not None:
                qs = getattr(view_instance, "queryset", None)
                if qs is not None and hasattr(qs, "model"):
                    model = qs.model
                
                if model is None and hasattr(view_instance, "get_queryset"):
                    try:
                        qs = view_instance.get_queryset()
                        if qs is not None and hasattr(qs, "model"):
                            model = qs.model
                    except Exception:
                        pass
                
                # Try serializer.Meta.model
                if model is None and hasattr(view_instance, "get_serializer_class"):
                    try:
                        serializer_class = view_instance.get_serializer_class()
                        meta = getattr(serializer_class, "Meta", None)
                        model = getattr(meta, "model", None)
                    except Exception:
                        pass
            
            # 3b. View class-level queryset / model (for DRF generics & CBVs)
            if model is None and view_class is not None:
                qs = getattr(view_class, "queryset", None)
                if qs is not None and hasattr(qs, "model"):
                    model = qs.model
                
                if model is None and hasattr(view_class, "model"):
                    model = view_class.model
            
            # 4. Resolve object_id from URL kwargs
            kwargs = match.kwargs or {}
            if kwargs:
                # DRF semantics if view_instance exists
                if view_instance is not None:
                    lookup_field = getattr(view_instance, "lookup_field", "pk")
                    lookup_url_kwarg = getattr(view_instance, "lookup_url_kwarg", lookup_field)
                    
                    if lookup_url_kwarg in kwargs:
                        object_id = str(kwargs[lookup_url_kwarg])
                
                # Fallback to common patterns
                if not object_id:
                    for key in ["pk", "id", "object_id"]:
                        if key in kwargs:
                            object_id = str(kwargs[key])
                            break
            
            # 5. Build content_type if model is found
            if model is not None:
                try:
                    content_type = ContentType.objects.get_for_model(model)
                except Exception:
                    content_type = None
        except Exception:
            # Best-effort: never raise
            logger.debug("Failed to resolve related object", exc_info=True)
        
        return content_type, object_id
    
    def _resolve_action_and_change_context(
        self, method: str, object_id: str, activity_ctx: dict
    ) -> tuple[str, dict, dict, dict, str, dict]:
        """Resolve action and instance change context."""
        explicit_action = activity_ctx.get("action")
        custom_action = activity_ctx.get("custom_action", "")
        custom_payload = activity_ctx.get("custom_payload", {})
        instance_before = activity_ctx.get("instance_before", {})
        instance_after = activity_ctx.get("instance_after", {})
        instance_diff = activity_ctx.get("instance_diff", {})
        
        method_upper = method.upper() if method else ""
        
        if explicit_action is not None and explicit_action != "":
            action = explicit_action
        elif custom_action and (explicit_action is None or explicit_action == ""):
            action = "CUSTOM"
        else:
            # Default action mapping based on HTTP method
            if method_upper == "GET":
                action = "VIEW"
            elif method_upper == "POST":
                has_object_context = bool(object_id)
                has_instance_before = bool(instance_before)
                if has_object_context or has_instance_before:
                    action = "UPDATE"
                else:
                    action = "CREATE"
            elif method_upper in ("PUT", "PATCH"):
                action = "UPDATE"
            elif method_upper == "DELETE":
                action = "DELETE"
            else:
                action = method_upper or ""
        
        return action, instance_before, instance_after, instance_diff, custom_action, custom_payload
    
    def _create_request_activity(
        self,
        method: str, path: str, full_path: str,
        http_status: int, response_time_ms: float, view_name: str, route_name: str,
        request_id: str, incident: Any,
        user: Any, is_authenticated: bool, ip_address: Any, user_agent: str,
        content_type: Any, object_id: str,
        request_headers: dict, request_body: str,
        response_headers: dict, response_body: str,
        action: str, instance_before: dict, instance_after: dict, instance_diff: dict,
        custom_action: str, custom_payload: dict,
        config: Any,
    ) -> None:
        """Create RequestActivity record in database."""
        try:
            # Sanitize JSON fields to ensure all values are JSON-serializable
            # This converts UUID, datetime, Decimal, etc. to strings
            instance_before = sanitize_for_json(instance_before)
            instance_after = sanitize_for_json(instance_after)
            instance_diff = sanitize_for_json(instance_diff)
            custom_payload = sanitize_for_json(custom_payload)
            
            RequestActivity.objects.create(
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

