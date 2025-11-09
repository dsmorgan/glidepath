"""Service functions for importing and managing account position CSV uploads and portfolio analysis."""

import csv
import re
from io import StringIO
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, DecimalField
from django.db.models.functions import Coalesce
from .models import AccountUpload, AccountPosition, User, Portfolio, Fund


def normalize_symbol(symbol: str) -> str:
    """
    Normalize a symbol by removing non-alphanumeric characters except hyphens.

    Examples:
        "FCASH**" -> "FCASH"
        "BTC" -> "BTC"
    """
    if not symbol:
        return ""
    # Remove ** and other special characters, keep only letters, numbers, and hyphens
    normalized = re.sub(r'[^A-Za-z0-9-]', '', symbol)
    return normalized.strip()


def extract_file_datetime(file_content: str) -> str:
    """
    Extract the file datetime string from the CSV content.

    Expected format at the end of file:
    "Date downloaded Nov-08-2025 7:54 p.m ET"
    """
    lines = file_content.strip().split('\n')

    # Look for the date line in the last few lines
    for line in reversed(lines[-5:]):
        if 'Date downloaded' in line:
            # Remove quotes if present
            date_str = line.strip().strip('"')
            return date_str

    return "Date not found in file"


def is_valid_position_row(row: dict) -> bool:
    """
    Check if a CSV row represents a valid position (has a symbol).

    Returns False for:
    - Rows where only first column has data
    - Rows with blank Symbol field
    - Informational/footer rows
    """
    symbol = (row.get('Symbol') or '').strip()

    # Must have a symbol
    if not symbol:
        return False

    # Must have account number
    if not (row.get('Account Number') or '').strip():
        return False

    return True


@transaction.atomic
def import_fidelity_csv(file_obj, user: User, filename: str) -> AccountUpload:
    """
    Import a Fidelity portfolio positions CSV file.

    Args:
        file_obj: File object containing CSV data
        user: User who is uploading the file
        filename: Original filename of the upload

    Returns:
        AccountUpload object

    Raises:
        ValueError: If CSV format is invalid or required data is missing
    """
    # Read the file content
    try:
        content = file_obj.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8-sig')  # Handle BOM if present
    except Exception as e:
        raise ValueError(f"Error reading file: {str(e)}")

    # Extract file datetime from the bottom of the file
    file_datetime = extract_file_datetime(content)

    # Parse CSV
    csv_file = StringIO(content)
    try:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
    except Exception as e:
        raise ValueError(f"Error parsing CSV: {str(e)}")

    if not rows:
        raise ValueError("CSV file is empty")

    # Check for duplicate upload - if exists, delete it first
    existing_uploads = AccountUpload.objects.filter(
        user=user,
        upload_type='fidelity',
        filename=filename
    )
    existing_uploads.delete()

    # Filter valid position rows
    valid_rows = [row for row in rows if is_valid_position_row(row)]

    if not valid_rows:
        raise ValueError("No valid position data found in CSV file")

    # Create AccountUpload record
    upload = AccountUpload.objects.create(
        user=user,
        file_datetime=file_datetime,
        upload_type='fidelity',
        filename=filename,
        entry_count=len(valid_rows)
    )

    # Create AccountPosition records
    for row in valid_rows:
        AccountPosition.objects.create(
            upload=upload,
            account_number=(row.get('Account Number') or '').strip(),
            account_name=(row.get('Account Name') or '').strip(),
            symbol=normalize_symbol(row.get('Symbol') or ''),
            description=(row.get('Description') or '').strip(),
            quantity=(row.get('Quantity') or '').strip(),
            last_price=(row.get('Last Price') or '').strip(),
            last_price_change=(row.get('Last Price Change') or '').strip(),
            current_value=(row.get('Current Value') or '').strip(),
            todays_gain_loss_dollar=(row.get("Today's Gain/Loss Dollar") or '').strip(),
            todays_gain_loss_percent=(row.get("Today's Gain/Loss Percent") or '').strip(),
            total_gain_loss_dollar=(row.get('Total Gain/Loss Dollar') or '').strip(),
            total_gain_loss_percent=(row.get('Total Gain/Loss Percent') or '').strip(),
            percent_of_account=(row.get('Percent Of Account') or '').strip(),
            cost_basis_total=(row.get('Cost Basis Total') or '').strip(),
            average_cost_basis=(row.get('Average Cost Basis') or '').strip(),
            type=(row.get('Type') or '').strip(),
        )

    return upload


def get_portfolio_analysis(portfolio: Portfolio) -> dict:
    """
    Analyze a portfolio and generate breakdown data for charts and tables.

    Returns a dict with:
    - class_breakdown: Class-level allocation
    - category_breakdown: Category-level allocation
    - ticker_breakdown: Ticker-level allocation
    - category_details: Detailed breakdown by category with symbols and subtotals
    - total_value: Total portfolio value
    """
    from decimal import Decimal, ROUND_HALF_UP

    # Get portfolio items
    portfolio_items = portfolio.items.all()
    if not portfolio_items:
        return {
            'class_breakdown': {},
            'category_breakdown': {},
            'ticker_breakdown': {},
            'category_details': [],
            'total_value': Decimal('0.00'),
        }

    # Get account numbers and symbols from portfolio
    account_symbols = list(portfolio_items.values_list('account_number', 'symbol'))

    # Get the most recent account upload for each account number
    latest_uploads = {}
    for account_number, symbol in account_symbols:
        if account_number not in latest_uploads:
            latest_upload = AccountUpload.objects.filter(
                user=portfolio.user,
                accountposition__account_number=account_number
            ).order_by('-created_at').first()
            if latest_upload:
                latest_uploads[account_number] = latest_upload

    # Aggregate positions by symbol
    symbol_totals = {}  # symbol -> total current value (as Decimal)
    for account_number, symbol in account_symbols:
        upload = latest_uploads.get(account_number)
        if not upload:
            continue

        positions = AccountPosition.objects.filter(
            upload=upload,
            account_number=account_number,
            symbol=symbol
        )

        for position in positions:
            # Parse current value, handling $ and commas
            current_value_str = position.current_value.replace('$', '').replace(',', '').strip()
            try:
                current_value = Decimal(current_value_str) if current_value_str else Decimal('0')
            except:
                current_value = Decimal('0')

            if symbol not in symbol_totals:
                symbol_totals[symbol] = Decimal('0')
            symbol_totals[symbol] += current_value

    # Build breakdowns by looking up fund information
    class_breakdown = {}  # class_name -> total value
    category_breakdown = {}  # category_name -> total value
    ticker_breakdown = {}  # ticker -> total value
    category_details = {}  # category_name -> {'total': value, 'symbols': {...}}

    for symbol, value in symbol_totals.items():
        ticker_breakdown[symbol] = value

        # Look up fund to get class and category
        fund = Fund.objects.filter(ticker=symbol).first()

        if fund and fund.category:
            category = fund.category
            asset_class = category.asset_class

            # Track class breakdown
            if asset_class.name not in class_breakdown:
                class_breakdown[asset_class.name] = Decimal('0')
            class_breakdown[asset_class.name] += value

            # Track category breakdown
            if category.name not in category_breakdown:
                category_breakdown[category.name] = Decimal('0')
            category_breakdown[category.name] += value

            # Track category details
            if category.name not in category_details:
                category_details[category.name] = {
                    'asset_class': asset_class.name,
                    'total': Decimal('0'),
                    'symbols': {}
                }
            category_details[category.name]['total'] += value
            category_details[category.name]['symbols'][symbol] = value
        else:
            # Unknown category
            if 'Unknown' not in category_details:
                category_details['Unknown'] = {
                    'asset_class': 'Unknown',
                    'total': Decimal('0'),
                    'symbols': {}
                }
            category_details['Unknown']['total'] += value
            category_details['Unknown']['symbols'][symbol] = value
            if 'Unknown' not in class_breakdown:
                class_breakdown['Unknown'] = Decimal('0')
            class_breakdown['Unknown'] += value
            if 'Unknown' not in category_breakdown:
                category_breakdown['Unknown'] = Decimal('0')
            category_breakdown['Unknown'] += value

    # Calculate total value
    total_value = sum(symbol_totals.values()) if symbol_totals else Decimal('0')

    # Format category details for template
    formatted_category_details = []
    for category_name in sorted(category_details.keys()):
        details = category_details[category_name]
        formatted_category_details.append({
            'category': category_name,
            'asset_class': details['asset_class'],
            'subtotal': details['total'],
            'symbols': [
                {'ticker': ticker, 'value': value}
                for ticker, value in sorted(details['symbols'].items())
            ]
        })

    return {
        'class_breakdown': {k: float(v) for k, v in class_breakdown.items()},
        'category_breakdown': {k: float(v) for k, v in category_breakdown.items()},
        'ticker_breakdown': {k: float(v) for k, v in ticker_breakdown.items()},
        'category_details': formatted_category_details,
        'total_value': float(total_value),
    }
