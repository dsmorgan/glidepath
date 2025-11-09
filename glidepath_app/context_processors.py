"""Context processors for Glidepath application."""

from .models import User


def users_context(request):
    """Add all users and the selected user to the template context."""
    all_users = User.objects.all().order_by('username')
    selected_user = None

    # Get selected user from session
    selected_user_id = request.session.get('selected_user_id')
    if selected_user_id:
        try:
            selected_user = User.objects.get(id=selected_user_id)
        except User.DoesNotExist:
            # Clear invalid session data
            request.session.pop('selected_user_id', None)

    return {
        'all_users': all_users,
        'selected_user': selected_user,
    }
