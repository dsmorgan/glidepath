"""Authentication middleware for Glidepath application."""

from django.shortcuts import redirect
from django.urls import reverse


class AuthenticationMiddleware:
    """Middleware to enforce authentication on all views except login and OAuth."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # List of paths that don't require authentication
        public_paths = [
            reverse('login'),
        ]

        # Check if current path requires authentication
        is_public = request.path in public_paths

        # Allow all OAuth/OIDC endpoints without authentication
        # These are needed for users to initiate login and handle callbacks
        if request.path.startswith('/auth/idp/') and '/oidc/' in request.path:
            is_public = True
        # Also allow with trailing slash
        if request.path.rstrip('/').startswith('/auth/idp/') and '/oidc/' in request.path:
            is_public = True

        if not is_public:
            # Check if user is authenticated
            if not request.session.get('user_id'):
                # Redirect to login page
                return redirect('login')

        response = self.get_response(request)
        return response
