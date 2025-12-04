# Installation Guide

This guide helps you install and set up `django-blackbox` in your Django project.

## Prerequisites

- Python 3.10 or higher
- Django 3.2 or higher
- Django REST Framework 3.14 or higher (optional, for API features)

## Installation Steps

### Installing from Source (Development)

If you're developing the library yourself or want to use the latest development version:

1. **Clone or navigate to the repository:**

```bash
cd path/to/django-server-incidents
```

2. **Install in editable mode:**

```bash
pip install -e .
```

This installs the package in "editable" mode, so any changes you make to the code are immediately reflected without reinstalling.

3. **Install with optional dependencies:**

```bash
pip install -e ".[ulid]"
```

4. **Install with development dependencies:**

```bash
pip install -e .[dev]
```

The package will now be available in your Python environment. Continue with the setup steps below to configure it in your Django project.

---

### Installing from PyPI (Production)

If the package is published on PyPI:

```bash
pip install django-blackbox
```

Or for ULID-based incident IDs:

```bash
pip install django-blackbox[ulid]
```

---

## Setup Steps

### 1. Add to INSTALLED_APPS

Edit your `settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # ... your other apps
    'django_blackbox',  # Add this
]
```

### 2. Add Middleware

Add the middleware **near the top** of your `MIDDLEWARE` setting:

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    
    # Add these three lines near the top
    'django_blackbox.middleware.RequestIDMiddleware',
    'django_blackbox.middleware.ActivityLoggingMiddleware',  # Log all requests (optional)
    'django_blackbox.middleware.Capture5xxMiddleware',
    
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

### 3. For Django REST Framework Projects

If you're using DRF, add this to your settings:

```python
REST_FRAMEWORK = {
    # ... your other DRF settings
    'EXCEPTION_HANDLER': 'django_blackbox.drf.exception_handler.incident_exception_handler',
}
```

### 4. Configure Database Migrations

Run migrations to create the Incident table:

```bash
python manage.py makemigrations django_blackbox
python manage.py migrate
```

### 5. (Optional) Configure Settings

Add optional configuration to your `settings.py`:

#### Basic Configuration

```python
DJANGO_BLACKBOX = {
    'ENABLED': True,
    'EXPOSE_JSON_ERROR_BODY': True,
    'GENERIC_ERROR_MESSAGE': 'Something went wrong. Please contact support with the Incident ID.',
    'REDACT_HEADERS': ['authorization', 'cookie'],
    'REDACT_FIELDS': ['password', 'token', 'secret'],
    'RETENTION_DAYS': 90,
}
```

#### Return 400 Instead of 500

If you want to return HTTP 400 (Bad Request) instead of 500 (Internal Server Error) for actual server errors:

```python
DJANGO_BLACKBOX = {
    'RETURN_400_INSTEAD_OF_500': True,
}
```

This is useful when you want to avoid exposing that the server had an internal error to the client.

#### Custom Error Format

You can customize the error response format using `CUSTOM_ERROR_FORMAT`:

```python
DJANGO_BLACKBOX = {
    'RETURN_400_INSTEAD_OF_500': True,
    'CUSTOM_ERROR_FORMAT': {
        'status': 500,
        'error_message': 'Server faced some internal error, please ask support team with this incident id: <incident_id>'
    }
}
```

**Note:** The `<incident_id>` placeholder will be automatically replaced with the actual incident ID.

#### Configure Which Status Codes to Capture

By default, only 5xx errors are captured. You can configure which status codes trigger incident creation:

```python
DJANGO_BLACKBOX = {
    # Capture all 5xx and specific 4xx codes
    'CAPTURE_STATUS_CODES': [
        (500, 599),  # All 5xx errors
        400,         # Specific 400 errors
        403,         # Forbidden errors
    ],
    
    # Or capture all errors
    'CAPTURE_STATUS_CODES': [(400, 599)],
    
    # Or only specific codes
    'CAPTURE_STATUS_CODES': [500, 502, 503],
}
```

This gives you control over which HTTP responses should create incidents.

**Example response:**
```json
{
  "status": 500,
  "error_message": "Server faced some internal error, please ask support team with this incident id: INCIDENT-0001"
}
```

### Capturing Full Stack Traces

If you catch exceptions in your views and want to include the full stack trace in incidents:

```python
from django_blackbox import create_error_response

def my_view(request):
    try:
        # your code that might fail
        part.append({...})
    except Exception as e:
        # Returns 500 response with stacktrace automatically included
        return create_error_response(
            f"An error occurred: {e}",
            e
        )
```

This ensures the complete stack trace with line numbers is captured in the incident.

See the main README.md for all available configuration options.

## Optional: Mount the Read-Only API

If you want to access incidents programmatically, add this to your main `urls.py`:

```python
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    # ... your other URL patterns
    path('django-blackbox/', include('django_blackbox.api.urls')),
]
```

Then access at: `http://your-domain/api/django-blackbox/incidents/<incident_id>/`

## Verify Installation

1. Create a test view that raises an exception:

```python
# myapp/views.py
from django.http import JsonResponse

def test_error(request):
    1 / 0  # This will trigger a 500 error
    return JsonResponse({"ok": True})
```

2. Visit the URL in your browser or make a request with `Accept: application/json`

3. Check that you receive:
   - A 500 status code
   - `X-Request-ID` header
   - `X-Incident-ID` header
   - JSON response body with incident_id

4. Check Django admin at `/admin/django_blackbox/incident/` - you should see the incident!

## Next Steps

- Configure your settings to match your needs
- Set up pruning of old incidents (see README)
- Customize the admin interface if needed
- Set up monitoring/alerts on the Incident model

## Troubleshooting

### "No module named 'server_incidents'"

- Make sure you ran `pip install django-blackbox`
- Check you're using the correct Python environment
- Try `pip list | grep django-server-incidents`

### "ModuleNotFoundError: No module named 'django.contrib.postgres.fields'"

- This is expected if you're not using Postgres
- The `tags` field will be a simple CharField instead of ArrayField
- This is handled automatically

### Migrations fail

- Make sure Django can access your database
- Check that your database supports the field types used
- For SQLite, ensure your version supports JSONField

### Incidents not appearing

- Check `DJANGO_BLACKBOX["ENABLED"]` is True
- Verify middleware is in the correct order
- Check `IGNORE_PATHS` to ensure your paths aren't ignored
- Look for `persist_error` in the fallback log file

## Support

For issues, questions, or contributions, please visit the project repository.

