"""Authentication middleware for Glidepath application."""

from django.shortcuts import redirect
from django.urls import reverse


class AuthenticationMiddleware:
    """Middleware to enforce authentication on all views except login."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # List of paths that don't require authentication
        public_paths = [
            reverse('login'),
        ]

        # Check if current path requires authentication
        if request.path not in public_paths:
            # Check if user is authenticated
            if not request.session.get('user_id'):
                # Redirect to login page
                return redirect('login')

        response = self.get_response(request)
        return response
