# Glidepath Administration Scripts

This directory contains administrative scripts for managing the Glidepath application.

## User Management Script

### Overview

The `manage_user.sh` script provides a secure way to create and manage internal user accounts. This is essential for initial system setup when authentication is enabled.

**Features:**
- Create new admin or regular user accounts
- Update existing users (change password, role, email)
- Promote users to administrator role
- Secure password input (hidden/masked)
- Password confirmation to prevent typos
- Internal users only (no identity provider integration)
- All users are created as enabled

### Usage

#### Basic Syntax

```bash
./scripts/manage_user.sh --username <username> --email <email> --role <admin|user> [--name <name>]
```

#### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `--username` | Yes | Username for the user account |
| `--email` | Yes | Email address for the user |
| `--role` | Yes | User role: `admin` or `user` |
| `--name` | No | Full name of the user (optional) |

### Examples

#### Create a New Administrator

```bash
./scripts/manage_user.sh \
  --username admin \
  --email admin@example.com \
  --role admin \
  --name "System Administrator"
```

When prompted, enter and confirm the password securely.

#### Create a Regular User

```bash
./scripts/manage_user.sh \
  --username john \
  --email john@example.com \
  --role user \
  --name "John Doe"
```

#### Update an Existing User

To change a user's password, role, or email, simply run the script with the existing username:

```bash
# Promote user to admin and change password
./scripts/manage_user.sh \
  --username john \
  --email john@example.com \
  --role admin
```

### Security Features

1. **Password Input**: Passwords are entered interactively and are hidden from the terminal display
2. **Password Confirmation**: Requires password to be entered twice to prevent typos
3. **Password Hashing**: Passwords are hashed using Django's secure password hashing (PBKDF2)
4. **Internal Users**: All users created via this script are internal (not linked to OAuth providers)
5. **Enabled by Default**: All users are created/updated as enabled accounts

### Docker Usage

The script automatically detects if Docker Compose is available and uses it to run the management command:

```bash
# With Docker Compose (automatic)
./scripts/manage_user.sh --username admin --email admin@example.com --role admin
```

### Direct Django Management Command

You can also use the Django management command directly:

```bash
# Via Docker Compose
docker-compose run --rm web python manage.py manage_user \
  --username admin \
  --email admin@example.com \
  --role admin \
  --name "Admin User"

# Or locally (if Django environment is set up)
python manage.py manage_user \
  --username admin \
  --email admin@example.com \
  --role admin \
  --name "Admin User"
```

### Output

The script provides clear feedback:

**Creating a new user:**
```
✓ User "admin" created successfully
  Status: New user created
  Email: admin@example.com
  Name: System Administrator
  Role: Administrator
  Type: Internal user
  Enabled: Yes
```

**Updating an existing user:**
```
✓ User "admin" updated successfully
  Status: Updated existing user
  Email: admin@example.com
  Name: System Administrator
  Role: Administrator
  Type: Internal user
  Enabled: Yes
```

### User Roles

- **Administrator** (`--role admin`): Full system access, can manage other users and system settings
- **User** (`--role user`): Standard user access, can manage their own portfolios and data

### Troubleshooting

**Script not executable:**
```bash
chmod +x scripts/manage_user.sh
```

**Email validation error:**
Ensure the email address is in valid format (user@domain.com)

**Password mismatch:**
The passwords entered must match exactly. Re-run the script if they don't match.

### Initial System Setup

When setting up Glidepath for the first time with authentication enabled:

1. Create an initial administrator account:
   ```bash
   ./scripts/manage_user.sh \
     --username admin \
     --email admin@yourcompany.com \
     --role admin \
     --name "System Admin"
   ```

2. Log in with the credentials you just created

3. Create additional user accounts as needed through the web interface or this script

### Notes

- This script is designed for **internal users only** (password-based authentication)
- For OAuth/OIDC users, use the identity provider configuration in the admin interface
- Users created via this script will have `identity_provider` set to `NULL`
- Users are always created as **enabled** (`disabled=False`)
- The script validates email addresses but does not send verification emails
