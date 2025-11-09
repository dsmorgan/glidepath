"""Service functions for importing and managing account position CSV uploads."""

import csv
import re
from io import StringIO
from django.db import transaction
from .models import AccountUpload, AccountPosition, User


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
