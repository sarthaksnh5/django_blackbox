"""
Middleware for request ID tracking and 5xx error capture.
"""
import sys

from django.utils.deprecation import MiddlewareMixin

from django_blackbox.conf import get_conf
from django_blackbox.request_id import get_request_id, new_request_id, set_request_id
from django_blackbox.services import log_5xx_response_and_decorate, log_exception_and_build_response


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

