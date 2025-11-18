"""Authorization decorators for Glidepath application."""

from functools import wraps
from django.http import HttpResponseForbidden


def admin_required(view_func):
    """Decorator to require admin privileges for a view."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check if user is admin
        if not request.session.get('is_admin', False):
            return HttpResponseForbidden("You do not have permission to perform this action. Administrator privileges required.")
        return view_func(request, *args, **kwargs)
    return wrapper
