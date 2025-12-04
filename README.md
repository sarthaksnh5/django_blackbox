# Django Black Box

A reusable, production-ready Django app that **captures and tracks HTTP errors** with rich metadata, persists them to the database, and returns user-facing error responses with **traceable Incident IDs**. Configure which status codes to capture, return custom error formats, and get complete stack traces for debugging.

## Features

- ✅ **Configurable capture** – Choose which HTTP status codes to capture (default: 5xx only)
- ✅ **Human-readable Incident IDs** – Simple IDs like `INCIDENT-0001` instead of UUIDs
- ✅ **Rich metadata** – Captures headers, request body, user info, IP, user agent, and full stacktraces in original format
- ✅ **Automatic deduplication** – Merges repeated incidents within a configurable time window
- ✅ **Traceable errors** – Every response includes `X-Incident-ID` and `X-Request-ID` headers
- ✅ **Custom error formats** – Define exactly how errors are displayed to users
- ✅ **Return 400 instead of 500** – Masks server errors as client errors for API clients
- ✅ **JSON error responses** – Optionally return JSON error body with incident ID for API clients
- ✅ **Stack trace helpers** – Easy-to-use helpers for capturing full stack traces
- ✅ **Django Admin integration** – View and manage incidents in Django admin
- ✅ **Optional read-only API** – Programmatic access to incident data
- ✅ **Database-agnostic** – Works with any Django-supported database
- ✅ **DRF integration** – Seamless integration with Django REST Framework
- ✅ **Fallback logging** – Writes to file if database save fails
- ✅ **Retention management** – Command to prune old incidents
- ✅ **Request Activity Logging** – Log all HTTP requests/responses (2xx, 3xx, 4xx, 5xx) with rich metadata
- ✅ **Instance Change Tracking** – Track before/after state for mutating operations (POST/PUT/PATCH/DELETE)
- ✅ **Custom Activity Labels** – Attach custom actions and payloads to request activities

## Installation

### Production Installation

```bash
pip install django-blackbox
```

For ULID-based incident IDs (shorter, sortable):

```bash
pip install django-blackbox[ulid]
```

### Development Installation

If you're developing the library or want to use it from source:

```bash
# Clone the repository
cd path/to/django-blackbox

# Install in editable mode
pip install -e .

# Or with optional dependencies
pip install -e ".[ulid]"
```

This installs the package in "editable" mode, so any changes you make to the code are immediately available without reinstalling.

## Quick Start

### 1. Add to INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    "django_blackbox",
]
```

### 2. Add Middleware

Add the middleware **near the top** of your `MIDDLEWARE` setting (before other exception-catching middleware):

```python
MIDDLEWARE = [
    "django_blackbox.middleware.RequestIDMiddleware",
    "django_blackbox.middleware.ActivityLoggingMiddleware",  # Log all requests
    "django_blackbox.middleware.Capture5xxMiddleware",
    # ... your other middleware
]
```

> **Note:** `ActivityLoggingMiddleware` should be placed **after** `RequestIDMiddleware` but **before** `Capture5xxMiddleware`.

### 3. For Django REST Framework Projects

Add the custom exception handler to your DRF configuration:

```python
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "django_blackbox.drf.exception_handler.incident_exception_handler"
}
```

### 4. Database Migrations

Run migrations to create the Incident and RequestActivity models:

```bash
python manage.py makemigrations django_blackbox
python manage.py migrate
```

> **Note:** Migration files are not pre-authored in the package. You generate them per your environment (e.g., Postgres, MySQL, SQLite).

### 5. Configure Settings (Optional)

Add to your `settings.py`:

```python
DJANGO_BLACKBOX = {
    "ENABLED": True,
    "EXPOSE_JSON_ERROR_BODY": True,
    "GENERIC_ERROR_MESSAGE": "Something broke on our side. We've logged it. Share the Incident ID with support.",
    "RETENTION_DAYS": 90,
    
    # Data storage: mask sensitive data by default
    "REDACT_SENSITIVE_DATA": True,  # Set False to store all data in original format
    
    # Return 400 instead of 500 for server errors
    "RETURN_400_INSTEAD_OF_500": False,
    
    # Custom error response format
    "CUSTOM_ERROR_FORMAT": {
        "status": 500,
        "error_message": "Server faced some internal error, please ask support team with this incident id: <incident_id>"
    },
    # Activity logging settings
    "ACTIVITY_LOG_ENABLED": True,
    "ACTIVITY_LOG_SAMPLE_RATE": 1.0,  # 0.0-1.0
    "ACTIVITY_LOG_IGNORE_PATHS": [r"^/health/", r"^/metrics"],
    "STORE_RESPONSE_BODY": False,  # Set True to capture response bodies
    "MAX_RESPONSE_BODY_BYTES": 1024,
    
    # ... see Configuration for full list
}
```

## What Users See on 5xx

### Response Headers

Every captured response includes headers:

- `X-Request-ID`: Unique identifier for the request (e.g., `015f6863-0fec-4823-9c77-5c635ae1c412`)
- `X-Incident-ID`: Human-readable incident ID (e.g., `INCIDENT-0001`)

### JSON Response (API clients)

If the client sends `Accept: application/json` or uses DRF, and `EXPOSE_JSON_ERROR_BODY=True`:

```json
{
  "detail": "Something broke on our side. We've logged it. Share the Incident ID with support.",
  "incident_id": "INCIDENT-0001"
}
```

**Note:** Status code may be **400** or **500** depending on your `RETURN_400_INSTEAD_OF_500` configuration.

### Custom Error Format

If you configure `CUSTOM_ERROR_FORMAT`:

```json
{
  "status": 500,
  "error_message": "Server faced some internal error, please ask support team with this incident id: INCIDENT-0001",
  "incident_id": "INCIDENT-0001"
}
```

### HTML Response (browsers)

For HTML requests, Django's default 500 template is shown (or a custom template via `OVERRIDE_500_TEMPLATE`).

## Configuration

All settings are optional with sensible defaults.

### Core Settings

```python
DJANGO_BLACKBOX = {
    # Enable/disable the middleware
    "ENABLED": True,
    
    # Add X-Request-ID header to all responses
    "ADD_REQUEST_ID_HEADER": True,
    
    # Add X-Incident-ID header to 5xx responses
    "ADD_INCIDENT_ID_HEADER": True,
    
    # Return JSON error body for API clients
    "EXPOSE_JSON_ERROR_BODY": True,
    
    # Generic error message shown to users
    "GENERIC_ERROR_MESSAGE": "Something broke on our side. We've logged it. Share the Incident ID with support.",
    
    # Include incident_id in JSON response body
    "INCLUDE_INCIDENT_ID_IN_BODY": True,
}
```

### Capture Settings

```python
DJANGO_BLACKBOX = {
    # Capture full stacktraces
    "CAPTURE_STACKTRACE": True,
    
    # Capture exceptions
    "CAPTURE_EXCEPTIONS": True,
    
    # Capture non-exception 5xx responses
    "CAPTURE_RESPONSE_5XX": True,
    
    # Which HTTP status codes should trigger incident capture
    "CAPTURE_STATUS_CODES": [(500, 599)],  # Default: all 5xx
    # You can customize this:
    # [(500, 599), 400]  # All 5xx plus 400
    # [500, 502, 503]    # Specific codes only
    # [(400, 599)]       # All 4xx and 5xx
    
    # Paths to ignore (regex patterns)
    "IGNORE_PATHS": [
        r"^/health/",
        r"^/metrics",
    ],
    
    # Exception classes to ignore (dotted paths)
    "IGNORE_EXCEPTIONS": [
        "django.http.Http404",
        "django.core.exceptions.PermissionDenied",
    ],
    
    # Sample rate (0.0 to 1.0) for high-traffic sites
    "SAMPLE_RATE": 1.0,
}
```

### Data Collection Settings

```python
DJANGO_BLACKBOX = {
    # Maximum bytes to store for request body
    "MAX_BODY_BYTES": 2048,
    
    # Content types to store body for
    "STORE_BODY_CONTENT_TYPES": [
        "application/json",
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    ],
    
    # Store data in original format (no masking)
    "REDACT_SENSITIVE_DATA": True,  # Set False for original format
    "REDACT_MASK": "[REDACTED]",
    "REDACT_HEADERS": ["authorization", "cookie", "set-cookie", "x-api-key"],
    "REDACT_FIELDS": ["password", "token", "access_token", "refresh_token", "secret", "otp"],
}
```


### Deduplication Settings

```python
DJANGO_BLACKBOX = {
    # Time window (seconds) to merge duplicate incidents
    "DEDUP_WINDOW_SECONDS": 300,
    
    # Days to retain incidents
    "RETENTION_DAYS": 90,
}
```

### Fallback Settings

```python
DJANGO_BLACKBOX = {
    # Write to JSONL file if DB save fails
    "FALLBACK_FILE_LOG": True,
    
    # Path to fallback log file
    "FALLBACK_FILE_PATH": "server_incidents_fallback.log",
}
```

### Advanced Settings

```python
DJANGO_BLACKBOX = {
    # Custom user resolution function (dotted path)
    "USER_RESOLUTION_CALLABLE": "myapp.utils.get_user_id",
    
    # Custom 500 template (dotted path)
    "OVERRIDE_500_TEMPLATE": "myapp/errors/500.html",
    
    # Return original 5xx status code (don't mask)
    "RETURN_ORIGINAL_500_STATUS": True,
    
    # Return 400 instead of 500 for server errors (useful for API clients)
    "RETURN_400_INSTEAD_OF_500": False,
    
    # Status codes to capture (supports ranges and specific codes)
    "CAPTURE_STATUS_CODES": [(500, 599)],  # Default: all 5xx
    # Examples:
    # [(500, 599), 400]  # 5xx plus 400
    # [500, 502, 503]    # Specific codes
    # [(400, 499), (500, 599)]  # All 4xx and 5xx
    
    # Custom error response format (replaces default)
    "CUSTOM_ERROR_FORMAT": {
        "status": 500,
        "error_message": "Server faced some internal error, please ask support team with this incident id: <incident_id>"
    },
}
```

**Note:** The `<incident_id>` placeholder in `CUSTOM_ERROR_FORMAT` will be automatically replaced with the actual incident ID (e.g., "INCIDENT-0001").

**Example with custom format:**
```python
DJANGO_BLACKBOX = {
    "RETURN_400_INSTEAD_OF_500": True,
    "CUSTOM_ERROR_FORMAT": {
        "status": 500,
        "error_message": "Internal server error. Contact support with incident id: <incident_id>",
        "severity": "high"
    }
}
```

This will return a 400 response with:
```json
{
  "status": 500,
  "error_message": "Internal server error. Contact support with incident id: INCIDENT-0001",
  "severity": "high",
  "incident_id": "INCIDENT-0001"
}
```

## Django Admin Integration

Once installed, incidents are available in Django admin at `/admin/django_blackbox/incident/`.

### Features

- **List view** with filters by status, HTTP status, date range
- **Search** by path, incident_id, request_id, exception class
- **Detail view** with collapsible panels for:
  - Request information (method, path, headers)
  - User information (user_id, IP, user agent)
  - Exception details (class, message, stacktrace)
  - Request body preview
- **Bulk actions**:
  - Mark as Acknowledged
  - Mark as Resolved (sets `resolved_at` automatically)
  - Mark as Suppressed

### Customization

You can override the admin in your app:

```python
from django_blackbox.admin import IncidentAdmin
from django_blackbox.models import Incident

# Customize fields, list_display, etc.
```

## Request Activity Logging

The `ActivityLoggingMiddleware` logs **every HTTP request/response** (2xx, 3xx, 4xx, and 5xx) to the `RequestActivity` model, providing comprehensive audit trails and debugging capabilities.

### Features

- **All Status Codes** – Captures 2xx, 3xx, 4xx, and 5xx responses
- **Rich Metadata** – Request/response headers, bodies, user info, IP, user agent, response time
- **View Resolution** – Automatically captures view name and route name
- **Related Objects** – Links to model instances via GenericForeignKey
- **Incident Linking** – Automatically links to `Incident` objects when 5xx errors occur
- **Sampling & Filtering** – Configurable sample rates and path ignore patterns

### Configuration

```python
DJANGO_BLACKBOX = {
    # Enable/disable activity logging
    "ACTIVITY_LOG_ENABLED": True,
    
    # Sample rate (0.0-1.0) for high-traffic sites
    "ACTIVITY_LOG_SAMPLE_RATE": 1.0,
    
    # Paths to ignore (regex patterns)
    "ACTIVITY_LOG_IGNORE_PATHS": [
        r"^/health/",
        r"^/metrics",
        r"^/static/",
    ],
    
    # Response body logging (optional, disabled by default)
    "STORE_RESPONSE_BODY": False,
    "MAX_RESPONSE_BODY_BYTES": 1024,
}
```

### Instance Change Tracking

For mutating operations (POST/PUT/PATCH/DELETE), you can track the **before** and **after** state of model instances.

#### Using the Helper Function

```python
from django_blackbox.activity import set_request_activity_change

def update_user(request, user_id):
    user = User.objects.get(id=user_id)
    instance_before = model_to_dict(user)  # Or use serializer
    
    # Perform update
    user.name = "New Name"
    user.save()
    
    instance_after = model_to_dict(user)
    
    # Attach change context to request
    set_request_activity_change(
        request,
        instance_before=instance_before,
        instance_after=instance_after,
        action="update",
        custom_action="user_profile_updated",
        custom_payload={"changed_by": request.user.id},
    )
    
    return JsonResponse({"status": "ok"})
```

#### Using the Decorator (DRF ViewSets)

```python
from rest_framework import viewsets
from django_blackbox.activity import log_request_activity_change

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
    @log_request_activity_change(
        action="update",
        custom_action="user_profile_updated"
    )
    def update(self, request, *args, **kwargs):
        # The decorator automatically captures:
        # - instance_before: from self.get_object()
        # - instance_after: from serializer.instance
        return super().update(request, *args, **kwargs)
    
    @log_request_activity_change(
        action="create",
        custom_action="user_created"
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)
    
    @log_request_activity_change(
        action="delete",
        custom_action="user_deleted"
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
```

The decorator automatically:
- Captures `instance_before` by calling `self.get_object()` before the operation
- Captures `instance_after` from `serializer.instance` after the operation
- Computes a diff between before/after states
- Stores everything in the `RequestActivity` record

#### Manual Instance Tracking

You can also manually set attributes on the view or request:

```python
@log_request_activity_change(
    action="update",
    instance_before_attr="_instance_before",  # Attribute on view/request
    instance_after_attr="_instance_after",
    extra_payload_callable=lambda req, resp: {"custom": "data"},
)
def update(self, request, *args, **kwargs):
    self._instance_before = self.get_object()
    result = super().update(request, *args, **kwargs)
    self._instance_after = self.get_object()
    return result
```

### Viewing Activities

Activities are available in Django admin at `/admin/django_blackbox/requestactivity/` and via the read-only API at `/api/activities/`.

## Optional Read-Only API

Mount the API under your URLconf for programmatic access:

```python
# urls.py
from django.urls import include, path

urlpatterns = [
    path("api/", include("django_blackbox.api.urls")),
]
```

### Endpoints

- `GET /api/incidents/` – List all incidents
- `GET /api/incidents/<incident_id>/` – Retrieve a single incident
- `GET /api/activities/` – List all request activities
- `GET /api/activities/<id>/` – Retrieve a single activity

The API uses DRF's `ReadOnlyModelViewSet`, providing automatic pagination, filtering, and search capabilities.

### Filtering Activities

The activities endpoint supports filtering by:
- `method` – HTTP method (GET, POST, etc.)
- `http_status` – Status code
- `user` – User ID
- `action` – Action label (create, update, delete)
- `custom_action` – Custom action label
- `request_id` – Request ID
- `is_authenticated` – Boolean

Example:
```
GET /api/activities/?method=POST&http_status=200&action=update
```

### Permissions

Default: Requires staff authentication. Override by setting:

```python
from django_blackbox.api.permissions import DEFAULT_PERMISSION_CLASS

# In your DRF settings or view
```

## Management Commands

### Prune Old Incidents

Delete incidents older than the retention period:

```bash
python manage.py prune_incidents
```

Options:

```bash
# Custom retention days
python manage.py prune_incidents --older-than=120

# Dry run (see what would be deleted)
python manage.py prune_incidents --dry-run
```

## Example Usage

### Triggering an Incident

A view that raises an exception:

```python
from django.http import JsonResponse

def boom(request):
    1 / 0  # Triggers 500
    return JsonResponse({"ok": True})
```

Client receives:

```
HTTP/1.1 500 Internal Server Error
X-Request-ID: 123e4567-e89b-12d3-a456-426614174000
X-Incident-ID: INCIDENT-0001

{
  "detail": "Something broke on our side. We've logged it. Share the Incident ID with support.",
  "incident_id": "INCIDENT-0001"
}
```

### Non-Exception 5xx

A view that returns an explicit 5xx:

```python
from django.http import HttpResponse

def bad_gateway(request):
    return HttpResponse("Upstream error", status=502)
```

An incident is still created with the HTTP status code.

### 4xx Errors Not Captured (by default)

```python
from django.http import JsonResponse

def not_found(request):
    return JsonResponse({"error": "Not found"}, status=404)
```

No incident is created for 4xx errors by default. However, you can configure this:

```python
DJANGO_BLACKBOX = {
    # Capture all errors including 4xx
    "CAPTURE_STATUS_CODES": [(400, 599)],
    
    # Or specific 4xx codes
    "CAPTURE_STATUS_CODES": [(500, 599), 400, 403, 429],
}
```

## Data Storage

### Masking Sensitive Data (Default)

By default, sensitive data is masked for privacy. Headers like `Authorization`, `Cookie`, and request body fields like `password`, `token` are redacted before storage.

```python
DJANGO_BLACKBOX = {
    "REDACT_SENSITIVE_DATA": True,  # Default: mask sensitive data
    "REDACT_HEADERS": ["authorization", "cookie", "set-cookie", "x-api-key"],
    "REDACT_FIELDS": ["password", "token", "access_token", "refresh_token", "secret", "otp"],
    "REDACT_MASK": "[REDACTED]",
}
```

### Store Original Data (For Debugging)

To store all data in its original format (useful for debugging), set `REDACT_SENSITIVE_DATA` to `False`:

```python
DJANGO_BLACKBOX = {
    "REDACT_SENSITIVE_DATA": False,  # Store all data in original format
}
```

**⚠️ Warning:** Storing original data (including authentication tokens) should only be used in development or secure environments with proper access controls.

### Body Truncation

Request bodies are truncated to `MAX_BODY_BYTES` (default 2048 bytes) to prevent storing extremely large payloads.

## Deduplication

Incidents with the same signature (exception class + normalized message + path) within the `DEDUP_WINDOW_SECONDS` window are merged:

- `occurrence_count` is incremented
- `occurred_at` is updated to the latest time
- Fields are safely merged

To disable: set `DEDUP_WINDOW_SECONDS: 0`.

## Fallback Logging

If the database write fails, the incident is written to a JSONL file:

```json
{"timestamp": "2024-01-15T10:30:00Z", "request_id": "...", "path": "/test", "http_status": 500, ...}
```

Configure the file path:

```python
DJANGO_BLACKBOX = {
    "FALLBACK_FILE_PATH": "/var/log/server_incidents.log",
}
```

## Troubleshooting

### Incidents Not Appearing

1. Check `ENABLED` is `True`
2. Verify middleware order (should be near the top)
3. Check `IGNORE_PATHS` or `IGNORE_EXCEPTIONS`
4. Check `SAMPLE_RATE` is not too low

### No X-Request-ID Header

1. Ensure `RequestIDMiddleware` is in `MIDDLEWARE`
2. Check `ADD_REQUEST_ID_HEADER` is `True`

### No JSON Error Body

1. Check `EXPOSE_JSON_ERROR_BODY` is `True`
2. Ensure client sends `Accept: application/json`
3. For DRF, ensure exception handler is configured

### Database Errors

Check the fallback log file (`FALLBACK_FILE_PATH`) for JSONL entries.

## FAQ

**Q: Does it capture 4xx errors?**  
A: By default, no. Only server-side failures (5xx) are captured. But you can configure this with `CAPTURE_STATUS_CODES`:

```python
DJANGO_BLACKBOX = {
    "CAPTURE_STATUS_CODES": [(400, 599)],  # Capture all 4xx and 5xx
}
```

**Q: How do I capture specific status codes?**  
A: Use the `CAPTURE_STATUS_CODES` setting:

```python
DJANGO_BLACKBOX = {
    # Capture only specific codes
    "CAPTURE_STATUS_CODES": [500, 502, 503],
    
    # Or capture ranges
    "CAPTURE_STATUS_CODES": [(500, 599)],
    
    # Or both
    "CAPTURE_STATUS_CODES": [(500, 599), 400, 429],
}
```

**Q: What are the Incident IDs like?**  
A: Human-readable IDs like `INCIDENT-0001`, `INCIDENT-0002`, etc. (not UUIDs)

**Q: How do I get full stack traces in incidents?**  
A: Use the helper function in your views:

```python
from django_blackbox import create_error_response

try:
    # your code
except Exception as e:
    return create_error_response("Error occurred", e)
```

**Q: Can I return 400 instead of 500 for server errors?**  
A: Yes, set `RETURN_400_INSTEAD_OF_500: True` in your configuration.

**Q: Will it change my 5xx status code to 200?**  
A: No. The status code is preserved (or changed to 400 if configured).

**Q: Can I use my own HTML template?**  
A: Yes, set `OVERRIDE_500_TEMPLATE` to a dotted path.

**Q: Does it work with multiple databases?**  
A: Yes, Django's database routing is respected.

**Q: Can I use this with async Django?**  
A: The middleware uses contextvars which work with async.

**Q: How does sampling work?**  
A: `SAMPLE_RATE: 0.5` means 50% of incidents are captured.

**Q: What data is stored?**  
A: By default, sensitive data (auth tokens, passwords) is masked for privacy. You can configure this:

```python
DJANGO_BLACKBOX = {
    "REDACT_SENSITIVE_DATA": False,  # Store original data for debugging
}
```

**Q: Can I store authorization tokens in original format?**  
A: Yes, set `REDACT_SENSITIVE_DATA: False` in settings. Use this only in secure environments with proper access controls.

**Q: What is Request Activity Logging?**  
A: A feature that logs **every HTTP request/response** (not just errors) to the `RequestActivity` model. Useful for audit trails, debugging, and analytics.

**Q: Does activity logging capture all requests?**  
A: Yes, by default it captures all requests (2xx, 3xx, 4xx, 5xx). You can configure sampling rates and ignore paths to reduce volume.

**Q: How do I track instance changes?**  
A: Use `set_request_activity_change()` helper or the `@log_request_activity_change` decorator. See the "Instance Change Tracking" section above.

**Q: Can I disable activity logging?**  
A: Yes, set `ACTIVITY_LOG_ENABLED: False` in your `DJANGO_BLACKBOX` settings.

## Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/sarthaksnh5/django_blackbox
cd django-blackbox

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with all dependencies
pip install -e ".[ulid,dev]"
```

### Running Tests

```bash
# Run all tests
python manage.py test tests

# Run specific test file
python manage.py test tests.test_models

# Run with coverage
pip install coverage
coverage run --source='django_blackbox' manage.py test tests
coverage report
```

### Building the Package

```bash
# Install build tools
pip install build twine

# Build distribution packages
python -m build

# This creates dist/ directory with .whl and .tar.gz files
```

### Installing from Local Source

```bash
# Install in editable mode (changes reflect immediately)
pip install -e .

# Install specific version
pip install -e ".[ulid]"

# Install for development with testing tools
pip install -e ".[dev]"
```

### Running a Test Django Project

```bash
# Create a test Django project
django-admin startproject testproject
cd testproject

# Add server_incidents to INSTALLED_APPS and MIDDLEWARE in settings.py
# Run migrations
python manage.py makemigrations django_blackbox
python manage.py migrate

# Create test views and verify incidents are captured
```

## License

MIT License - see `LICENSE` file for details.

## Contributing

Contributions welcome! Please open an issue or pull request.

