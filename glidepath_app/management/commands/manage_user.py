"""
Django management command for user administration.

This command allows administrators to:
- Create new admin or regular users
- Update existing users (change password, role)
- Set users as administrators

Usage:
    python manage.py manage_user --username <username> --email <email> --role <admin|user> [--name <name>]
"""

import getpass
import sys
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from glidepath_app.models import User


class Command(BaseCommand):
    help = 'Create or update internal users with secure password handling'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            type=str,
            required=True,
            help='Username for the user'
        )
        parser.add_argument(
            '--email',
            type=str,
            required=True,
            help='Email address for the user'
        )
        parser.add_argument(
            '--role',
            type=str,
            required=True,
            choices=['admin', 'user'],
            help='Role for the user (admin or user)'
        )
        parser.add_argument(
            '--name',
            type=str,
            required=False,
            default='',
            help='Full name for the user (optional)'
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        role_str = options['role']
        name = options.get('name', '')

        # Convert role string to integer
        role = 0 if role_str == 'admin' else 1
        role_display = 'Administrator' if role == 0 else 'User'

        # Validate email
        try:
            validate_email(email)
        except ValidationError:
            raise CommandError(f'Invalid email address: {email}')

        # Check if user exists
        user_exists = User.objects.filter(username=username).exists()

        # Prompt for password securely
        self.stdout.write(self.style.WARNING('\nPassword input (hidden):'))
        password = getpass.getpass('Enter password: ')

        if not password:
            raise CommandError('Password cannot be empty')

        password_confirm = getpass.getpass('Confirm password: ')

        if password != password_confirm:
            raise CommandError('Passwords do not match')

        # Hash the password
        hashed_password = make_password(password)

        try:
            if user_exists:
                # Update existing user
                user = User.objects.get(username=username)
                user.email = email
                user.name = name
                user.role = role
                user.password = hashed_password
                user.identity_provider = None  # Internal user
                user.disabled = False  # Enabled
                user.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✓ User "{username}" updated successfully'
                    )
                )
                self.stdout.write(f'  Status: Updated existing user')
            else:
                # Create new user
                user = User.objects.create(
                    username=username,
                    email=email,
                    name=name,
                    role=role,
                    password=hashed_password,
                    identity_provider=None,  # Internal user
                    disabled=False  # Enabled
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✓ User "{username}" created successfully'
                    )
                )
                self.stdout.write(f'  Status: New user created')

            # Display user details
            self.stdout.write(f'  Email: {email}')
            self.stdout.write(f'  Name: {name if name else "(not set)"}')
            self.stdout.write(f'  Role: {role_display}')
            self.stdout.write(f'  Type: Internal user')
            self.stdout.write(f'  Enabled: Yes')
            self.stdout.write('')

        except Exception as e:
            raise CommandError(f'Error managing user: {str(e)}')
