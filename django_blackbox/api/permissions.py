"""
Permissions for the read-only API.
"""
from rest_framework import permissions


class IsStaffOrReadOnly(permissions.BasePermission):
    """
    Permission class that allows read access only to staff users.
    
    For non-staff users, this denies all access.
    """

    def has_permission(self, request, view):
        """Check if user has permission to access."""
        # Allow read access for staff users
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_staff
        # Deny write access
        return False


# Default permission class
DEFAULT_PERMISSION_CLASS = IsStaffOrReadOnly

