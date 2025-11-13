# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Glidepath is a Django web application for managing investment allocation rules (glidepatches) based on retirement age. It allows users to import CSV-based allocation rules, visualize them with charts, and export them back to CSV.

**Core Functionality:**
- Import glidepath rules from CSV files
- Store asset class and category allocations by retirement age bands
- Visualize allocations with interactive charts (stacked area, pie)
- Export rules back to CSV format

## Project Structure

### Directory Layout
```
glidepath/
├── glidepath_project/        # Django project configuration
│   ├── settings.py          # Settings (SQLite DB, minimal middleware)
│   ├── urls.py              # URL routing
│   └── wsgi.py              # WSGI application
├── glidepath_app/           # Main application
│   ├── models.py            # Database models
│   ├── views.py             # View logic (upload, export, charting)
│   ├── services.py          # Business logic (import/export)
│   ├── forms.py             # Form definitions
│   ├── tests.py             # Unit tests
│   ├── migrations/          # Database migrations
│   ├── templates/           # HTML templates
│   ├── static/              # Static assets
│   └── management/          # Django management commands
│       └── commands/        # Custom management commands
│           └── manage_user.py  # User administration command
├── scripts/                 # Administration scripts
│   ├── manage_user.sh       # User management wrapper script
│   └── README.md            # Scripts documentation
└── manage.py                # Django management script
```

### Database Models (glidepath_app/models.py)

#### Entity Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ALLOCATION MANAGEMENT                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  RuleSet                    GlidepathRule              AssetClass            │
│  ────────                   ──────────────             ──────────            │
│  id (PK)                    id (PK)                    id (PK)               │
│  name (UNIQUE)              ruleset_id (FK) ──────→ name (UNIQUE)           │
│                             gt_retire_age                                    │
│                             lt_retire_age                                    │
│                                                                               │
│                    ▲                                                          │
│                    │                                                          │
│                    └────────────┬──────────────────────────────────┐          │
│                                 │                                  │          │
│                                 │                                  │          │
│                         ClassAllocation                  AssetCategory        │
│                         ────────────────                 ──────────────       │
│                         id (PK)                         id (PK)              │
│                         rule_id (FK) ──┐               name                 │
│                         asset_class_id  │               asset_class_id (FK)  │
│                         (FK) ───────────┼──────→        unique: (name,      │
│                         percentage      │               asset_class)         │
│                                         │                                    │
│                                         │                                    │
│                                  ▼      │                                    │
│                         CategoryAllocation               Fund                │
│                         ───────────────────             ─────                │
│                         id (PK)                         id (PK)              │
│                         rule_id (FK)                    ticker (UNIQUE)      │
│                         asset_category_id (FK)──→       name                 │
│                         percentage                      category_id (FK)──→  │
│                                                         created_at            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        PORTFOLIO & HOLDINGS MANAGEMENT                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  User                      Portfolio                   PortfolioItem         │
│  ────                      ─────────                   ─────────────         │
│  id (UUID, PK)             id (UUID, PK)              id (UUID, PK)         │
│  username (UNIQUE)         user_id (FK) ────────┐     portfolio_id (FK)──┐  │
│  email (UNIQUE)            name                 │     account_number     │  │
│  name                      ruleset_id (FK)      │     symbol             │  │
│  identity_provider_id      (FK, nullable)       │     unique: (portfolio,│  │
│  (FK, nullable)            year_born            │     account_number,    │  │
│  role                      retirement_age       │     symbol)            │  │
│  disabled                  created_at           │                        │  │
│  password (internal only)  updated_at           │                        │  │
│  created_at                                     │                        │  │
│  updated_at                                     │                        │  │
│         │                                       │                        │  │
│         │                                       └────────────────────────┘  │
│         │                                                                    │
│         │                          AccountUpload      AccountPosition        │
│         │                          ──────────────     ────────────────       │
│         │                          id (UUID, PK)      id (UUID, PK)          │
│         │                          user_id (FK) ───┐  upload_id (FK) ──┐    │
│         │                          upload_datetime  │  account_number   │    │
│         │                          file_datetime    │  account_name     │    │
│         │                          upload_type      │  symbol           │    │
│         │                          filename         │  description      │    │
│         │                          entry_count      │  quantity         │    │
│         │                                           │  last_price       │    │
│         │                                           │  ... (price data) │    │
│         │                                           │  type             │    │
│         │                                           │  [and more fields]│    │
│         └──────────────────────────────────────────┴──────────────────┘    │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    AUTHENTICATION & CONFIGURATION                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  IdentityProvider                          APISettings                       │
│  ─────────────────                         ───────────                       │
│  id (UUID, PK)                             id (PK)                           │
│  name (UNIQUE)                             alpha_vantage_api_key            │
│  type (choice: OAuth2/OIDC)                finnhub_api_key                  │
│  redirect_url                              polygon_api_key                  │
│  auto_provision_users                      eodhd_api_key                    │
│  client_id                                 updated_at                        │
│  client_secret                                                               │
│  authorization_url                                                           │
│  token_url                                                                   │
│  identity_path                                                               │
│  email_path                                                                  │
│  name_path                                                                   │
│  scopes                                                                      │
│  created_at                                                                  │
│  updated_at                                                                  │
│         │                                                                    │
│         └──→ User (identity_provider_id FK)                                 │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Model Descriptions

**RuleSet** - Container for a set of glidepath rules (one row = one CSV import)
- `name`: Unique name for the ruleset
- Related to: GlidepathRule (1:many), Portfolio (1:many)

**GlidepathRule** - An allocation rule for a retirement age band
- `ruleset`: Foreign key to RuleSet
- `gt_retire_age`: Greater than retirement age (lower bound of band)
- `lt_retire_age`: Less than retirement age (upper bound of band)
- Validation: Ages are clamped to [-100, 100], ensures no overlaps/gaps
- Related to: ClassAllocation (1:many), CategoryAllocation (1:many)

**AssetClass** - Top-level asset categories (Stocks, Bonds, Crypto, Other)
- `name`: Asset class name (unique)
- Related to: AssetCategory (1:many), ClassAllocation (1:many), Fund (optional)

**ClassAllocation** - Percentage allocation to an asset class within a rule
- `rule`: Foreign key to GlidepathRule
- `asset_class`: Foreign key to AssetClass
- `percentage`: Decimal percentage (must sum to 100% per rule)
- Unique together on (rule, asset_class)

**AssetCategory** - Subcategories within an asset class (e.g., "Large Cap" under Stocks)
- `name`: Category name
- `asset_class`: Foreign key to AssetClass
- Unique together on (name, asset_class)
- Related to: CategoryAllocation (1:many), Fund (1:many)

**CategoryAllocation** - Percentage allocation to a category within a rule
- `rule`: Foreign key to GlidepathRule
- `asset_category`: Foreign key to AssetCategory
- `percentage`: Decimal percentage
- Unique together on (rule, asset_category)

**APISettings** - Stores API keys and settings for financial data sources
- Singleton table (only one row with id=1)
- `alpha_vantage_api_key`: Alpha Vantage API key
- `finnhub_api_key`: Finnhub API key
- `polygon_api_key`: Polygon.io API key
- `eodhd_api_key`: EODHD API key
- `updated_at`: Timestamp of last update

**Fund** - Stores investment fund information
- `ticker`: Fund ticker symbol (unique)
- `name`: Fund name
- `category`: Foreign key to AssetCategory (nullable, optional)
- `created_at`: Creation timestamp
- Related to: AssetCategory (many:1 optional)

**IdentityProvider** - Stores OAuth2/OIDC identity provider configurations
- `id`: UUID primary key
- `name`: Provider name (unique)
- `type`: Provider type (currently only OAuth2/OIDC)
- `redirect_url`: OAuth redirect URL
- `auto_provision_users`: Boolean flag to auto-create users on first login
- `client_id`: OAuth client ID
- `client_secret`: OAuth client secret
- `authorization_url`: OAuth authorization endpoint
- `token_url`: OAuth token endpoint
- `identity_path`: JSON path to user identity in provider response
- `email_path`: JSON path to email in provider response
- `name_path`: JSON path to name in provider response
- `scopes`: Space-separated OAuth scopes
- Related to: User (1:many)

**User** - Stores user account information
- `id`: UUID primary key
- `username`: Username (unique)
- `email`: Email address (unique)
- `name`: Full name
- `identity_provider`: Foreign key to IdentityProvider (nullable)
- `role`: User role (0=Administrator, 1=User)
- `disabled`: Boolean flag for account status
- `password`: Password hash (only for internal users)
- `created_at`: Account creation timestamp
- `updated_at`: Last updated timestamp
- Related to: IdentityProvider (many:1 optional), AccountUpload (1:many), Portfolio (1:many)

**AccountUpload** - Stores metadata about uploaded account position CSV files
- `id`: UUID primary key
- `user`: Foreign key to User
- `upload_datetime`: Timestamp when file was uploaded
- `file_datetime`: Raw date/time string from CSV file
- `upload_type`: Type of upload (currently 'fidelity')
- `filename`: Original filename
- `entry_count`: Number of positions in the upload
- Related to: User (many:1), AccountPosition (1:many)

**AccountPosition** - Stores individual position records from account CSV uploads
- `id`: UUID primary key
- `upload`: Foreign key to AccountUpload
- `account_number`: Account identifier
- `account_name`: Account name
- `symbol`: Normalized ticker symbol
- `description`: Position description
- `quantity`: Quantity held (string)
- `last_price`: Last trade price (string)
- `last_price_change`: Price change amount (string)
- `current_value`: Current market value (string)
- `todays_gain_loss_dollar`: Daily P&L in dollars (string)
- `todays_gain_loss_percent`: Daily P&L percentage (string)
- `total_gain_loss_dollar`: Total P&L in dollars (string)
- `total_gain_loss_percent`: Total P&L percentage (string)
- `percent_of_account`: Percentage of account (string)
- `cost_basis_total`: Total cost basis (string)
- `average_cost_basis`: Average cost per share (string)
- `type`: Position type (string)
- Related to: AccountUpload (many:1)

**Portfolio** - Stores portfolio configurations for grouping account positions
- `id`: UUID primary key
- `user`: Foreign key to User
- `name`: Portfolio name
- `ruleset`: Foreign key to RuleSet (nullable, optional)
- `year_born`: Birth year for target allocation calculation
- `retirement_age`: Target retirement age for allocation
- `created_at`: Creation timestamp
- `updated_at`: Last updated timestamp
- Unique together on (user, name)
- Related to: User (many:1), RuleSet (many:1 optional), PortfolioItem (1:many)

**PortfolioItem** - Stores which account+symbol combinations are included in a portfolio
- `id`: UUID primary key
- `portfolio`: Foreign key to Portfolio
- `account_number`: Account identifier
- `symbol`: Ticker symbol
- Unique together on (portfolio, account_number, symbol)
- Related to: Portfolio (many:1)

### Key Business Logic (glidepath_app/services.py)

**import_glidepath_rules(file_obj)** - CSV import engine
- Parses CSV with required columns: `gt-retire-age`, `lt-retire-age`
- Supports asset class columns (Stocks, Bonds, Crypto, Other)
- Supports category columns in format `ClassName:CategoryName`
- Validates:
  - Categories must match their asset class allocations
  - No gaps or overlaps in age bands (must cover -100 to 100)
  - Class + category allocations sum to 100%
- Returns created RuleSet object
- Uses atomic transaction for data consistency

**export_glidepath_rules(ruleset)** - CSV export engine
- Generates CSV with all rules and allocations
- Omits asset classes/categories with 0% allocation
- Maintains column order: ages, then classes, then categories

**Percentage Parsing (_parse_percent)**
- Handles percent signs, decimals, empty values
- Rounds to 2 decimal places using ROUND_HALF_UP

### View Layer (glidepath_app/views.py)

**upload_rules(request)** - Main view for rule management
- GET: Shows upload form and current rules
- POST with file: Imports new ruleset
- POST with delete: Removes a ruleset
- Generates three chart datasets from rule data:
  - `class_chart`: Stacked area chart by asset class
  - `category_chart`: Stacked area chart by category
  - `class_pie_chart`: Pie chart for age -7 (example age)
- Returns full HTML template on GET, partial template for HTMX requests

**export_rules(request)** - CSV download endpoint
- Returns CSV file with filename matching ruleset name

**Chart Building (_build_chart_data)** - Data transformation for visualization
- Converts database rules into Chart.js compatible JSON
- Labels include "earlier" (-100) and "later" boundaries
- Uses color generation with cycling defaults and HSL fallback
- Lightens colors for category-level breakdown

## Common Development Commands

```bash
# Start development server (with auto-reload and migrations)
docker-compose up --build

# Access the app at http://localhost:8000/

# Run tests
docker-compose run --rm web python manage.py test

# Run a specific test
docker-compose run --rm web python manage.py test glidepath_app.tests.ImportRulesTests.test_import_sample_csv

# Apply migrations
docker-compose run --rm web python manage.py migrate

# Create superuser (if needed for admin access)
docker-compose run --rm web python manage.py createsuperuser

# Django shell (interactive Python with Django context)
docker-compose run --rm web python manage.py shell

# View SQL for a migration
docker-compose run --rm web python manage.py sqlmigrate glidepath_app [migration_number]
```

## User Administration

### Managing Users with the Admin Script

The `scripts/manage_user.sh` script provides a secure way to create and manage internal user accounts. This is essential for initial system setup when authentication is enabled.

**Create an admin user:**
```bash
./scripts/manage_user.sh \
  --username admin \
  --email admin@example.com \
  --role admin \
  --name "System Administrator"
```

**Create a regular user:**
```bash
./scripts/manage_user.sh \
  --username john \
  --email john@example.com \
  --role user \
  --name "John Doe"
```

**Update existing user (change password/role):**
```bash
./scripts/manage_user.sh \
  --username john \
  --email john@example.com \
  --role admin
```

The script will:
- Prompt for password securely (hidden input)
- Require password confirmation
- Hash passwords using Django's secure password hashing (PBKDF2)
- Create internal users only (not linked to OAuth providers)
- Enable users by default
- Report whether user was created or updated

**Container Runtime Support:**
The script automatically detects and uses available container runtimes in priority order:
1. docker-compose
2. podman-compose (works on systems using Podman)
3. docker (direct commands, builds image if needed)
4. podman (direct commands, builds image if needed)
5. python3 (fallback with warning)

No local Python installation required when using containers.

See `scripts/README.md` for complete documentation.

**Django management command:**
```bash
# Via Docker Compose
docker-compose run --rm web python manage.py manage_user \
  --username admin \
  --email admin@example.com \
  --role admin \
  --name "Admin User"

# Via Podman Compose
podman-compose run --rm web python manage.py manage_user \
  --username admin \
  --email admin@example.com \
  --role admin \
  --name "Admin User"

# Via direct Podman
podman run --rm -it -v $(pwd):/app:z -w /app glidepath-web \
  python manage.py manage_user \
  --username admin \
  --email admin@example.com \
  --role admin

# Locally (if Django environment is set up)
python manage.py manage_user \
  --username admin \
  --email admin@example.com \
  --role admin \
  --name "Admin User"
```

## Architecture Notes

### Age Band Model
- Ages are stored as integers representing "years to/from retirement"
- Negative values represent "before retirement" (-100 = very young)
- Positive values represent "after retirement" (100 = very old)
- Bands are defined by `gt_retire_age` to `lt_retire_age`
- The full spectrum must be covered with no gaps or overlaps

### Two-Level Allocation
The system supports both broad (asset class) and detailed (category) allocations:
1. **Class level**: Direct percentages for Stocks, Bonds, Crypto, Other
2. **Category level**: Subcategories within each class (e.g., Stocks:Large Cap, Stocks:Small Cap)

When both are present, category allocations must sum to match their parent class allocation.

### CSV Format
```
gt-retire-age,lt-retire-age,Stocks,Bonds,Stocks:Large Cap,Stocks:Small Cap
-100,0,70,30,50,20
0,100,30,70,15,15
```
- Headers are normalized (spaces around colons removed)
- Percentages can include or omit the `%` symbol
- Zero percentages are omitted from exports
- Missing allocations default to 0%

### Frontend (HTMX)
- The `upload_rules` view detects HTMX requests and returns partial HTML (`rules.html`) instead of full page
- This enables dynamic rule list updates without full page reloads

## Testing Strategy

Tests in `glidepath_app/tests.py`:
- **test_import_sample_csv**: Validates import of sample CSV file and data creation
- **test_import_normalizes_and_export_skips_zero**: Verifies CSV normalization and export filtering
- **test_unique_ruleset_names**: Confirms duplicate ruleset naming with numeric suffixes
- **test_missing_years_raise_error**: Validates age band coverage validation
- **test_overlapping_years_raise_error**: Validates no overlapping age bands

Run tests with: `docker-compose run --rm web python manage.py test`

## Database

- Uses SQLite for development (configured in `settings.py`)
- Database file: `db.sqlite3` (created automatically)
- Migrations applied automatically on container startup
- For resetting: Remove `db.sqlite3` and restart container
