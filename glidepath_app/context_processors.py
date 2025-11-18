"""Context processors for Glidepath application."""

from .models import User


def users_context(request):
    """Add all users and the selected user to the template context."""
    # Get the currently logged-in user
    user_id = request.session.get('user_id')
    is_admin = request.session.get('is_admin', False)
    current_user = None
    selected_user = None
    all_users = []

    if user_id:
        try:
            current_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass

    # For admins, show all users and allow selection
    if is_admin and current_user:
        all_users = User.objects.all().order_by('username')

        # Get selected user from session (for admins viewing other users' data)
        selected_user_id = request.session.get('selected_user_id')
        if selected_user_id:
            try:
                selected_user = User.objects.get(id=selected_user_id)
            except User.DoesNotExist:
                # Clear invalid session data
                request.session.pop('selected_user_id', None)
                selected_user = current_user
        else:
            # Default to current user if no selection
            selected_user = current_user
    else:
        # For regular users, selected_user is always the logged-in user
        selected_user = current_user

    return {
        'all_users': all_users,
        'selected_user': selected_user,
        'current_user': current_user,
        'is_admin': is_admin,
    }
