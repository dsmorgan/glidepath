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
│   └── static/              # Static assets
└── manage.py                # Django management script
```

### Database Models (glidepath_app/models.py)

**RuleSet** - Container for a set of glidepath rules (one row = one CSV import)
- `name`: Unique name for the ruleset

**GlidepathRule** - An allocation rule for a retirement age band
- `ruleset`: Foreign key to RuleSet
- `gt_retire_age`: Greater than retirement age (lower bound of band)
- `lt_retire_age`: Less than retirement age (upper bound of band)
- Validation: Ages are clamped to [-100, 100], ensures no overlaps/gaps

**AssetClass** - Top-level asset categories (Stocks, Bonds, Crypto, Other)
- `name`: Asset class name

**ClassAllocation** - Percentage allocation to an asset class within a rule
- `rule`: Foreign key to GlidepathRule
- `asset_class`: Foreign key to AssetClass
- `percentage`: Decimal percentage (must sum to 100% per rule)

**AssetCategory** - Subcategories within an asset class (e.g., "Large Cap" under Stocks)
- `name`: Category name
- `asset_class`: Foreign key to AssetClass
- Unique together on (name, asset_class)

**CategoryAllocation** - Percentage allocation to a category within a rule
- Similar structure to ClassAllocation but for categories

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
