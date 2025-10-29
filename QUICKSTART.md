# Quick Start Guide

Get up and running with `django-blackbox` in 5 minutes.

## 1. Install

```bash
pip install django-blackbox
```

## 2. Update settings.py

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... existing apps
    'django_blackbox',
]
```

Add middleware:

```python
MIDDLEWARE = [
    'server_incidents.middleware.RequestIDMiddleware',
    'server_incidents.middleware.Capture5xxMiddleware',
    # ... rest of middleware
]
```

## 3. Run migrations

```bash
python manage.py makemigrations django_blackbox
python manage.py migrate
```

## 4. Test it

Create a test view in any app:

```python
# myapp/views.py
def test_error(request):
    1 / 0  # This causes a 500 error
    return HttpResponse("This won't be reached")
```

Make a request, and you'll get:

```
HTTP/1.1 500 Internal Server Error
X-Request-ID: 123e4567-e89b-12d3-a456-426614174000
X-Incident-ID: 2a7c8a7b-1c3d-4e5f-a6b7-c8d9e0f1a2b3

Content-Type: application/json
{
  "detail": "Something broke on our side. We've logged it. Share the Incident ID with support.",
  "incident_id": "2a7c8a7b-1c3d-4e5f-a6b7-c8d9e0f1a2b3"
}
```

## 5. View in Admin

Go to `/admin/django_blackbox/incident/` to see all incidents.

## Done!

That's it. Every 5xx error now has a traceable Incident ID. Your users can share this with support, and you can track patterns in Django admin.

## Next Steps

- Read [README.md](README.md) for full documentation
- See [INSTALLATION.md](INSTALLATION.md) for detailed setup
- Configure settings for your needs (see README "Configuration" section)

