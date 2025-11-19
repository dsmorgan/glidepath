# Glidepath

Glidepath is a Django web application for managing investment allocation rules (glide paths) based on retirement age. It provides portfolio management capabilities with OAuth2/OIDC authentication support.

## Overview

Glidepath allows users to:
- **Import and manage glidepath rules** from CSV files with asset class and category allocations
- **Visualize allocations** with interactive charts (stacked area and pie charts)
- **Export rules** back to CSV format
- **Manage investment accounts and portfolios** with account position tracking
- **Track fund data** with categorization and preference rankings
- **Authenticate securely** via OAuth2/OIDC (e.g., Authentik) or internal credentials
- **Multi-user support** with role-based access control (Administrator/User)

## Architecture

- **Backend**: Django 4.2 with SQLite database
- **Frontend**: HTML/Tailwind CSS with HTMX for dynamic interactions
- **Authentication**: OAuth2/OIDC or local authentication
- **Deployment**: Docker/Podman with docker-compose

## Quick Start

### Prerequisites

- Docker and Docker Compose (or Podman and Podman Compose)
- Git

### Running the Application

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd glidepath
   ```

2. **Start the application**:
   ```bash
   docker-compose up --build
   ```

   The application will be available at `http://localhost:8000/`

   Database migrations apply automatically on startup.

3. **Create a user** (for internal authentication):
   ```bash
   ./scripts/manage_user.sh \
     --username john \
     --email john@example.com \
     --role user \
     --name "John Doe"
   ```

   For administrator access:
   ```bash
   ./scripts/manage_user.sh \
     --username admin \
     --email admin@example.com \
     --role admin \
     --name "System Administrator"
   ```

### Running Tests

```bash
docker-compose run --rm web python manage.py test
```

## Capabilities

### Rule Management
- Import CSV-based glidepath rules with:
  - Retirement age bands (from -100 to 100 years)
  - Asset class allocations (Stocks, Bonds, Crypto, Other)
  - Category-level breakdowns within each asset class
- Automatic validation:
  - Ensures age bands have no gaps or overlaps
  - Verifies allocations sum to 100%
- Export rules back to CSV format

### Portfolio Management
- Create and manage multiple portfolios per user
- Link portfolios to glidepath rulesets for target allocation tracking
- Specify retirement age and year born for allocation calculations
- Group account positions into portfolios

### Account Management
- Upload account position CSV files (Fidelity, E-Trade formats)
- Track holdings with real-time pricing data
- View portfolio analysis and allocation vs. target
- Map positions to asset categories

### Fund Database
- Maintain fund library with ticker symbols and names
- Categorize funds within asset categories
- Set preference rankings for fund recommendations

### Authentication & Security
- **OAuth2/OIDC Support**: Integrate with identity providers like Authentik, Okta, Azure AD
  - Automatic user provisioning
  - Multi-provider support
  - Secure token exchange
- **Local Authentication**: Internal user accounts with secure password hashing
- **Role-Based Access**: Administrator and User roles with appropriate permissions
- **Session Management**: Configurable session timeouts

## Configuration

### OAuth2/OIDC Setup

To enable OAuth authentication:

1. Configure an identity provider (e.g., Authentik)
2. Create an OAuth2 application with:
   - Redirect URI: `https://your-domain/auth/idp/{provider-id}/oidc/callback`
   - Scopes: `openid profile email`

3. Add the provider in Glidepath Settings → Identity Providers with:
   - Authorization URL
   - Token URL
   - Client ID and Secret
   - JSON paths for extracting: identity (sub), email, name

### API Keys

Store API keys for financial data sources in Settings → API Settings:
- Alpha Vantage API Key
- Finnhub API Key
- Polygon.io API Key
- EODHD API Key

## Development

### Database Commands

```bash
# Apply migrations
docker-compose run --rm web python manage.py migrate

# Create migrations
docker-compose run --rm web python manage.py makemigrations

# Django shell
docker-compose run --rm web python manage.py shell

# View SQL for a migration
docker-compose run --rm web python manage.py sqlmigrate glidepath_app [migration_number]
```

### Common Tasks

```bash
# Restart the application
docker-compose restart

# View logs
docker-compose logs -f web

# Access the container shell
docker-compose run --rm web bash
```

## Project Structure

```
glidepath/
├── glidepath_project/       # Django project configuration
│   ├── settings.py         # Project settings
│   ├── urls.py             # URL routing
│   └── wsgi.py             # WSGI application
├── glidepath_app/          # Main application
│   ├── models.py           # Database models
│   ├── views.py            # View logic
│   ├── services.py         # Business logic
│   ├── forms.py            # Form definitions
│   ├── tests.py            # Unit tests
│   ├── middleware.py       # Authentication middleware
│   ├── templates/          # HTML templates
│   ├── static/             # Static assets
│   └── management/         # Management commands
├── scripts/                # Administration scripts
├── db.sqlite3             # SQLite database (local development)
├── docker-compose.yml     # Docker compose configuration
├── Dockerfile             # Container definition
└── manage.py              # Django management script
```

## Documentation

- See [CLAUDE.md](CLAUDE.md) for detailed technical documentation and architecture notes
- See [scripts/README.md](scripts/README.md) for user management scripts

## Troubleshooting

### OAuth Login Issues

If OAuth login is not working:
1. Check that the Identity Provider configuration matches your IdP settings
2. Verify the redirect URI matches exactly (protocol, domain, path)
3. Ensure `auto_provision_users` is enabled if you want automatic user creation
4. Check application logs for detailed error messages

### Database Issues

If you encounter database errors:
```bash
# Reset database (loses all data)
rm db.sqlite3
docker-compose up --build
```

## Support

For issues and feature requests, please check the [documentation](CLAUDE.md) or create an issue in the repository.
