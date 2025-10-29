# How to Get Full Stack Trace in Your Views

## The Problem

When you catch an exception in a view and return a Response with status 500, the stack trace is not automatically captured because the exception was already caught.

## The Solution

You need to **include the stack trace in your view's response**. Here's how:

### **Option 1: Use the helper function (Recommended)**

Replace your try/except block with:

```python
from django_blackbox import create_error_response

def get_visit_report(self, request, *args, **kwargs):
    try:
        instance = self.get_object()
        # ... your existing code ...
        
        # Code that might raise AttributeError
        part.append({...})
        
        # ... rest of your code ...
        
    except Exception as e:
        # This automatically includes the full stack trace
        return create_error_response(
            f"An error occurred while generating the visit report: {str(e)}",
            e
        )
```

### **Option 2: Manually add stack trace**

If you prefer to keep your existing response structure:

```python
from django_blackbox import add_stacktrace_to_response
from rest_framework.response import Response
import traceback

def get_visit_report(self, request, *args, **kwargs):
    try:
        # your code
        instance = self.get_object()
        part.append({...})
    except Exception as e:
        # Log for debugging
        traceback.print_exc()
        
        # Create response
        response = Response(
            {"detail": f"An error occurred while generating the visit report: {str(e)}"}, 
            status=500
        )
        
        # Add stacktrace for incident logging
        add_stacktrace_to_response(response, e)
        
        return response
```

### **Option 3: Don't catch the exception (Best for debugging)**

Just remove the try/except and let the exception propagate:

```python
# BEFORE
def get_visit_report(self, request, *args, **kwargs):
    try:
        # code
        part.append({...})
    except Exception as e:
        return Response({"detail": str(e)}, status=500)

# AFTER
def get_visit_report(self, request, *args, **kwargs):
    # No try/except - let the exception propagate
    instance = self.get_object()
    part.append({...})
    # ... rest of code
```

This way, the full stack trace will be automatically captured.

## What You'll Get

After implementing any of the above options, your incident will include:

```json
{
  "exception_class": "builtins.AttributeError",
  "exception_message": "'CommissioningRequestPart' object has no attribute 'append'",
  "stacktrace": "Traceback (most recent call last):\n  File \"/path/to/file.py\", line 3403, in get_visit_report\n    part.append({...})\n    ^^^^^^^^^^^\nAttributeError: 'CommissioningRequestPart' object has no attribute 'append'\n\nFull file paths and line numbers will be included..."
}
```

## Quick Fix for Your Current Code

In your `abstract_views.py`, find:

```python
except Exception as e:
    # Handle errors gracefully
    import traceback
    traceback.print_exc()
    return Response({"detail": f"An error occurred while generating the visit report: {str(e)}"}, status=500)
```

Replace with:

```python
from django_blackbox import create_error_response

except Exception as e:
    import traceback
    traceback.print_exc()
    return create_error_response(
        f"An error occurred while generating the visit report: {str(e)}",
        e
    )
```

That's it! Now your incidents will have the full stack trace with line numbers.

