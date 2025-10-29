"""
Views for the read-only API.
"""
import json

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from django_blackbox.models import Incident
from .permissions import DEFAULT_PERMISSION_CLASS
from .serializers import IncidentSerializer


class IncidentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for Incident model.
    
    Provides:
    - GET /api/incidents/               - List all incidents
    - GET /api/incidents/{incident_id}/  - Retrieve a specific incident
    """
    
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer
    permission_classes = [AllowAny]
    # permission_classes = DEFAULT_PERMISSION_CLASS
    lookup_field = "request_id"  # Use incident_id instead of pk for lookups

    @action(detail=True, methods=["get"])
    def curl(self, request, *args, **kwargs):
        """
        Generate a complete curl command that reproduces the original request.
        
        Includes:
        - HTTP method
        - Full URL (path + query string)
        - All headers (Authorization, Content-Type, etc.)
        - Request body for POST/PUT/PATCH/DELETE methods
        """
        incident = self.get_object()
        
        # Build base URL (assuming localhost for example, can be customized)
        base_url = request.build_absolute_uri('/').rstrip('/')
        url = f"{base_url}{incident.path}"
        
        # Add query string if present
        if incident.query_string:
            # Check if path already has query params
            separator = '&' if '?' in url else '?'
            url = f"{url}{separator}{incident.query_string}"
        
        # Build curl command parts
        curl_parts = ["curl"]
        curl_parts.append("-X")
        curl_parts.append(incident.method)
        
        # Track which headers we've added to avoid duplicates
        added_headers = set()
        
        # Add headers
        if incident.headers:
            for header_name, header_value in incident.headers.items():
                header_lower = header_name.lower()
                # Skip host header as it's part of URL
                if header_lower != 'host':
                    curl_parts.append("-H")
                    # Escape quotes in header values
                    escaped_value = str(header_value).replace('"', '\\"')
                    curl_parts.append(f'"{header_name}: {escaped_value}"')
                    added_headers.add(header_lower)
        
        # Add body data for methods that typically send data
        body_methods = ['POST', 'PUT', 'PATCH', 'DELETE']
        if incident.method.upper() in body_methods and incident.body_preview:
            # Use the stored content_type if available, otherwise infer from headers
            content_type = incident.content_type
            if not content_type and incident.headers:
                content_type = incident.headers.get('Content-Type') or incident.headers.get('content-type')
            content_type = (content_type or '').lower()
            
            # Format body based on content type
            if 'application/json' in content_type:
                # JSON body - try to parse and format, otherwise use as-is
                try:
                    body_data = json.loads(incident.body_preview)
                    formatted_body = json.dumps(body_data, separators=(',', ':'))
                except (json.JSONDecodeError, TypeError):
                    # Not valid JSON, use as-is
                    formatted_body = incident.body_preview
                
                # Add Content-Type header only if not already present
                if 'content-type' not in added_headers:
                    curl_parts.append("-H")
                    curl_parts.append('"Content-Type: application/json"')
                
                curl_parts.append("-d")
                # Escape the JSON body for shell safety
                escaped_body = formatted_body.replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
                curl_parts.append(f'"{escaped_body}"')
                
            elif 'application/x-www-form-urlencoded' in content_type:
                # Form data
                if 'content-type' not in added_headers:
                    curl_parts.append("-H")
                    curl_parts.append('"Content-Type: application/x-www-form-urlencoded"')
                curl_parts.append("-d")
                escaped_body = incident.body_preview.replace('"', '\\"')
                curl_parts.append(f'"{escaped_body}"')
                
            elif 'multipart/form-data' in content_type:
                # Multipart form - note that exact boundary is needed
                if 'content-type' not in added_headers:
                    # Use original content type if available, otherwise default
                    original_ct = incident.content_type or 'multipart/form-data'
                    curl_parts.append("-H")
                    curl_parts.append(f'"Content-Type: {original_ct}"')
                curl_parts.append("-d")
                escaped_body = incident.body_preview.replace('"', '\\"')
                curl_parts.append(f'"{escaped_body}"')
                
            else:
                # Generic body data
                if incident.content_type and 'content-type' not in added_headers:
                    curl_parts.append("-H")
                    curl_parts.append(f'"Content-Type: {incident.content_type}"')
                curl_parts.append("-d")
                # Escape special characters for shell
                escaped_body = incident.body_preview.replace('"', '\\"').replace('\n', '\\n').replace('$', '\\$')
                curl_parts.append(f'"{escaped_body}"')
        
        # Add URL (must be last)
        curl_parts.append(url)
        
        # Join all parts
        curl_command = " ".join(curl_parts)
        
        return Response({
            "curl": curl_command,
            "method": incident.method,
            "url": url,
            "headers_count": len(incident.headers) if incident.headers else 0,
            "has_body": bool(incident.body_preview and incident.method.upper() in body_methods),
        })