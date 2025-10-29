# Configuration Examples

This document provides practical examples for configuring Django Black Box for different use cases.

## Example 1: Basic Setup (Default)

Captures 5xx errors and returns 500 status with incident ID in JSON response:

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "EXPOSE_JSON_ERROR_BODY": True,
}
```

**Response:**
```
HTTP/1.1 500 Internal Server Error
X-Request-ID: 123e4567-e89b-12d3-a456-426614174000
X-Incident-ID: INCIDENT-0001

{
  "detail": "Something broke on our side. We've logged it. Share the Incident ID with support.",
  "incident_id": "INCIDENT-0001"
}
```

---

## Example 2: Return 400 Instead of 500

Return 400 status for actual server errors (useful for API clients):

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "RETURN_400_INSTEAD_OF_500": True,
}
```

**Response:**
```
HTTP/1.1 400 Bad Request
X-Request-ID: 123e4567-e89b-12d3-a456-426614174000
X-Incident-ID: INCIDENT-0001

{
  "detail": "Something broke on our side. We've logged it. Share the Incident ID with support.",
  "incident_id": "INCIDENT-0001"
}
```

---

## Example 3: Custom Error Format (as per your requirement)

Return 400 with custom error format matching your exact requirements:

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "RETURN_400_INSTEAD_OF_500": True,
    "CUSTOM_ERROR_FORMAT": {
        "status": 500,
        "error_message": "Server faced some internal error, please ask support team with this incident id: <incident_id>"
    }
}
```

**Response:**
```
HTTP/1.1 400 Bad Request
X-Request-ID: 123e4567-e89b-12d3-a456-426614174000
X-Incident-ID: INCIDENT-0001

{
  "status": 500,
  "error_message": "Server faced some internal error, please ask support team with this incident id: INCIDENT-0001",
  "incident_id": "INCIDENT-0001"
}
```

**Note:** The `<incident_id>` placeholder is automatically replaced with the actual incident ID (e.g., "INCIDENT-0001").

---

## Example 4: Production Configuration with Privacy (Default)

Complete production setup with masking and retention:

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "EXPOSE_JSON_ERROR_BODY": True,
    "GENERIC_ERROR_MESSAGE": "An error occurred. Please contact support with the incident ID.",
    
    # Privacy settings (REDACT_SENSITIVE_DATA is True by default)
    "REDACT_SENSITIVE_DATA": True,  # Mask sensitive data
    "REDACT_HEADERS": ["authorization", "cookie", "x-api-key", "x-auth-token"],
    "REDACT_FIELDS": ["password", "token", "secret", "api_key", "private_key"],
    "REDACT_MASK": "[REDACTED]",
    "MAX_BODY_BYTES": 1024,  # Store smaller body previews
    
    # Ignore health checks and metrics
    "IGNORE_PATHS": [
        r"^/health/",
        r"^/metrics",
        r"^/ping",
    ],
    
    # Retention
    "RETENTION_DAYS": 30,
    
    # Fallback logging
    "FALLBACK_FILE_PATH": "/var/log/django_blackbox.log",
}
```

## Example 4b: Store Original Data (For Debugging)

Store all data in original format, including auth tokens (use only in secure environments):

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "EXPOSE_JSON_ERROR_BODY": True,
    "GENERIC_ERROR_MESSAGE": "An error occurred. Please contact support with the incident ID.",
    
    # Store original data (no masking)
    "REDACT_SENSITIVE_DATA": False,  # Store all data in original format
    "MAX_BODY_BYTES": 2048,
    
    # Retention
    "RETENTION_DAYS": 90,
    
    # Fallback logging
    "FALLBACK_FILE_PATH": "/var/log/django_blackbox.log",
}
```

**⚠️ Warning:** Only use `REDACT_SENSITIVE_DATA: False` in secure environments with proper access controls (e.g., internal services, development environments).

---

## Example 5: High-Traffic Site (Sampling)

For sites with high error volumes, use sampling:

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    
    # Capture 50% of incidents randomly
    "SAMPLE_RATE": 0.5,
    
    # Longer deduplication window to reduce noise
    "DEDUP_WINDOW_SECONDS": 600,  # 10 minutes
    
    # Don't capture stacktraces for all incidents
    "CAPTURE_STACKTRACE": True,
}
```

---

## Example 6: Custom Error Response with Additional Fields

Add custom fields to error responses:

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "RETURN_400_INSTEAD_OF_500": True,
    "CUSTOM_ERROR_FORMAT": {
        "status": "error",
        "code": 500,
        "message": "An internal error occurred. Reference ID: <incident_id>",
        "timestamp": None,  # Will be added automatically
        "incident_id": "<incident_id>"  # Explicitly add if you want
    }
}
```

**Response:**
```json
{
  "status": "error",
  "code": 500,
  "message": "An internal error occurred. Reference ID: INCIDENT-0001",
  "timestamp": "2024-10-28T17:15:15Z",
  "incident_id": "INCIDENT-0001"
}
```

---

## Example 7: Disable Stacktrace Capture

For sensitive applications, don't capture full stacktraces:

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "CAPTURE_STACKTRACE": False,  # Don't store full stacktraces
    
    # Only store exception class and message
    "CAPTURE_EXCEPTIONS": True,
}
```

---

## Example 8: Ignore Specific Exceptions

Don't capture certain exception types:

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    
    # Ignore validation errors and permission denied
    "IGNORE_EXCEPTIONS": [
        "django.core.exceptions.ValidationError",
        "django.core.exceptions.PermissionDenied",
    ],
}
```

---

## Example 9: Custom User Resolution

Resolve user IDs using a custom function:

```python
# myapp/utils.py
def get_user_identifier(request):
    """Return a user identifier string."""
    if hasattr(request, 'user') and request.user.is_authenticated:
        return f"{request.user.id}"
    return None

# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "USER_RESOLUTION_CALLABLE": "myapp.utils.get_user_identifier",
}
```

---

## Example 10: Configure Which Status Codes to Capture

By default, only 5xx errors create incidents. You can configure specific status codes or ranges:

```python
# settings.py
DJANGO_BLACKBOX = {
    # Capture all 5xx AND specific 4xx codes
    "CAPTURE_STATUS_CODES": [
        (500, 599),  # All 5xx errors
        400,         # Bad request errors
        403,         # Forbidden errors
        429,         # Rate limit errors
    ],
}
```

Or capture all errors:

```python
DJANGO_BLACKBOX = {
    # Capture all 4xx and 5xx errors
    "CAPTURE_STATUS_CODES": [(400, 599)],
}
```

Or only specific error codes:

```python
DJANGO_BLACKBOX = {
    # Only 500, 502, 503 (common upstream errors)
    "CAPTURE_STATUS_CODES": [500, 502, 503],
}
```

## Example 11: Minimal Configuration

Absolute minimum configuration:

```python
# settings.py
DJANGO_BLACKBOX = {
    "ENABLED": True,  # That's it!
}
```

All other settings use sensible defaults.

---

## Quick Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `ENABLED` | `True` | Enable/disable the middleware |
| `RETURN_400_INSTEAD_OF_500` | `False` | Return 400 instead of 500 for server errors |
| `CUSTOM_ERROR_FORMAT` | `None` | Custom JSON error response format |
| `CAPTURE_STATUS_CODES` | `[(500, 599)]` | Which HTTP status codes trigger incidents |
| `EXPOSE_JSON_ERROR_BODY` | `True` | Return JSON error body for API clients |
| `CAPTURE_STACKTRACE` | `True` | Capture full stacktraces |
| `REDACT_SENSITIVE_DATA` | `True` | Mask sensitive data (headers, body fields) |
| `REDACT_HEADERS` | `["authorization", ...]` | Headers to mask when REDACT_SENSITIVE_DATA is True |
| `REDACT_FIELDS` | `["password", ...]` | Body fields to mask when REDACT_SENSITIVE_DATA is True |
| `REDACT_MASK` | `"[REDACTED]"` | Mask string for sensitive data |
| `RETENTION_DAYS` | `90` | Days to keep incidents |
| `DEDUP_WINDOW_SECONDS` | `300` | Deduplication window |

---

## Testing Your Configuration

Create a test view to verify your configuration:

```python
# myapp/views.py
from django.http import JsonResponse

def test_error(request):
    """Test view that raises an error."""
    1 / 0  # This will trigger a 500 error
    return JsonResponse({"ok": True})
```

Then make a request and check:
1. HTTP status code (should match your configuration)
2. Response body format
3. Incident ID in headers and body
4. Check admin panel for the incident

---

For more details, see the main README.md file.

