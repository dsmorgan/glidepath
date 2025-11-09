"""Context processors for Glidepath application."""

from .models import User


def users_context(request):
    """Add all users to the template context."""
    return {
        'all_users': User.objects.all().order_by('username'),
    }
