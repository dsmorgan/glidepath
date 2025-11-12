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
    - class_breakdown: Class-level allocation (current)
    - category_breakdown: Category-level allocation (current)
    - target_class_breakdown: Target class allocation from glidepath rule
    - target_category_breakdown: Target category allocation from glidepath rule
    - category_details: Detailed breakdown by category with symbols and subtotals
    - total_value: Total portfolio value
    """
    from decimal import Decimal, ROUND_HALF_UP
    from datetime import datetime

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
                positions__account_number=account_number
            ).order_by('-upload_datetime').first()
            if latest_upload:
                latest_uploads[account_number] = latest_upload

    # Aggregate positions by (account_number, symbol) to track per-account holdings
    # Key: (account_number, symbol) -> Dict with value and quantity
    symbol_account_data = {}  # (account_number, symbol) -> {'value': Decimal, 'quantity': Decimal}
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

            # Parse quantity, handling commas
            quantity_str = position.quantity.replace(',', '').strip()
            try:
                quantity = Decimal(quantity_str) if quantity_str else Decimal('0')
            except:
                quantity = Decimal('0')

            # Store per-account data
            key = (account_number, symbol)
            if key not in symbol_account_data:
                symbol_account_data[key] = {'value': Decimal('0'), 'quantity': Decimal('0')}
            symbol_account_data[key]['value'] += current_value
            symbol_account_data[key]['quantity'] += quantity

    # Build breakdowns by looking up fund information
    class_breakdown = {}  # class_name -> total value
    category_breakdown = {}  # class_name:category_name -> total value
    ticker_breakdown = {}  # ticker -> total value
    category_details = {}  # class_name:category_name -> {'total': value, 'symbols': [...]}

    for (account_number, symbol), account_data in symbol_account_data.items():
        value = account_data['value']
        quantity = account_data['quantity']

        # Update total value tracking for ticker
        if symbol not in ticker_breakdown:
            ticker_breakdown[symbol] = Decimal('0')
        ticker_breakdown[symbol] += value

        # Look up fund to get class and category
        fund = Fund.objects.filter(ticker=symbol).first()

        if fund and fund.category:
            # Fund exists with a category assigned
            category = fund.category
            asset_class = category.asset_class

            # Create composite key: AssetClass:Category (e.g., "Stocks:International Market")
            category_key = f"{asset_class.name}:{category.name}"

            # Track class breakdown
            if asset_class.name not in class_breakdown:
                class_breakdown[asset_class.name] = Decimal('0')
            class_breakdown[asset_class.name] += value

            # Track category breakdown (using composite key to distinguish same-named categories)
            if category_key not in category_breakdown:
                category_breakdown[category_key] = Decimal('0')
            category_breakdown[category_key] += value

            # Track category details (using composite key to distinguish same-named categories)
            if category_key not in category_details:
                category_details[category_key] = {
                    'asset_class': asset_class.name,
                    'category_name': category.name,  # Store original category name separately
                    'total': Decimal('0'),
                    'symbols': []  # Changed to list for per-account entries
                }
            category_details[category_key]['total'] += value
            category_details[category_key]['symbols'].append({
                'account_number': account_number,
                'ticker': symbol,
                'value': value,
                'quantity': quantity,
                'fund_name': fund.name if fund else None,
                'preference': fund.preference if fund else None,
                'is_recommended': fund.is_recommended() if fund else False,
            })
        elif fund:
            # Fund exists but has no category assigned - treat as "Other"
            category_key = 'Other'
            if category_key not in category_details:
                category_details[category_key] = {
                    'asset_class': 'Other',
                    'category_name': 'Other',
                    'total': Decimal('0'),
                    'symbols': []  # Changed to list for per-account entries
                }
            category_details[category_key]['total'] += value
            category_details[category_key]['symbols'].append({
                'account_number': account_number,
                'ticker': symbol,
                'value': value,
                'quantity': quantity,
                'fund_name': fund.name,
                'preference': fund.preference,
                'is_recommended': fund.is_recommended(),
            })
            if 'Other' not in class_breakdown:
                class_breakdown['Other'] = Decimal('0')
            class_breakdown['Other'] += value
            if 'Other' not in category_breakdown:
                category_breakdown['Other'] = Decimal('0')
            category_breakdown['Other'] += value
        else:
            # Fund does not exist in database - treat as "Unknown"
            category_key = 'Unknown'
            if category_key not in category_details:
                category_details[category_key] = {
                    'asset_class': 'Unknown',
                    'category_name': 'Unknown',
                    'total': Decimal('0'),
                    'symbols': []  # Changed to list for per-account entries
                }
            category_details[category_key]['total'] += value
            category_details[category_key]['symbols'].append({
                'account_number': account_number,
                'ticker': symbol,
                'value': value,
                'quantity': quantity,
                'fund_name': None,
                'preference': None,
                'is_recommended': False,
            })
            if 'Unknown' not in class_breakdown:
                class_breakdown['Unknown'] = Decimal('0')
            class_breakdown['Unknown'] += value
            if 'Unknown' not in category_breakdown:
                category_breakdown['Unknown'] = Decimal('0')
            category_breakdown['Unknown'] += value

    # Calculate total value
    total_value = sum(ticker_breakdown.values()) if ticker_breakdown else Decimal('0')

    # Calculate target allocations from glidepath rule if available
    # Do this BEFORE formatting so we can add missing categories
    from datetime import datetime
    current_year = datetime.now().year

    target_class_breakdown = {}
    target_category_breakdown = {}
    years_to_retirement = None
    matching_rule = None

    if portfolio.ruleset and portfolio.year_born and portfolio.retirement_age:
        # Calculate years to retirement based on current year
        # Formula: current_year - year_born - retirement_age
        # Negative value = before retirement, Positive = after retirement
        years_to_retirement = current_year - portfolio.year_born - portfolio.retirement_age

        # Find the glidepath rule for this retirement age
        from .models import GlidepathRule
        matching_rule = GlidepathRule.objects.filter(
            ruleset=portfolio.ruleset,
            gt_retire_age__lte=years_to_retirement,
            lt_retire_age__gt=years_to_retirement
        ).first()

        if matching_rule:
            # Get class allocations
            for class_alloc in matching_rule.class_allocations.all():
                target_class_breakdown[class_alloc.asset_class.name] = float(class_alloc.percentage)

            # Get category allocations
            for cat_alloc in matching_rule.category_allocations.all():
                # Use composite key to distinguish categories with same name in different asset classes
                category_key = f"{cat_alloc.asset_category.asset_class.name}:{cat_alloc.asset_category.name}"
                target_category_breakdown[category_key] = float(cat_alloc.percentage)

                # Ensure all categories from glidepath rule are in category_details
                # even if they have no actual holdings
                if category_key not in category_details:
                    category_details[category_key] = {
                        'asset_class': cat_alloc.asset_category.asset_class.name,
                        'category_name': cat_alloc.asset_category.name,
                        'total': Decimal('0'),
                        'symbols': []  # Changed to list for per-account entries
                    }

    # Now format ALL category details for template (including newly added empty categories)
    formatted_category_details = []
    for category_key in sorted(category_details.keys()):
        details = category_details[category_key]
        subtotal_float = float(details['total'])

        # Calculate current percentage (always, even without glidepath rule)
        current_pct = (subtotal_float / float(total_value) * 100) if total_value > 0 else 0

        formatted_category_details.append({
            'category': details.get('category_name', category_key),  # Use category_name for display
            'asset_class': details['asset_class'],
            'subtotal': subtotal_float,  # Convert Decimal to float for JSON serialization
            'current_pct': round(current_pct, 2),  # Always include current percentage
            'symbols': [
                {
                    'account_number': symbol_data.get('account_number'),
                    'ticker': symbol_data.get('ticker'),
                    'value': float(symbol_data.get('value', 0)),  # Convert to float
                    'quantity': float(symbol_data.get('quantity', 0)),  # Convert to float
                    'price': (float(symbol_data.get('value', 0)) / float(symbol_data.get('quantity', 0))) if symbol_data.get('quantity', 0) > 0 else 0,  # Calculate price
                    'fund_name': symbol_data.get('fund_name'),
                    'preference': symbol_data.get('preference'),
                    'is_recommended': symbol_data.get('is_recommended', False),
                }
                for symbol_data in sorted(details['symbols'], key=lambda x: (x.get('account_number', ''), x.get('ticker', '')))
            ]
        })

    # Add target and difference information to category details if we have a matching rule
    if matching_rule:
        # Convert total_value to float for calculations to avoid Decimal/float type issues
        total_value_float = float(total_value)

        for category_item in formatted_category_details:
            category_name = category_item['category']
            asset_class_name = category_item['asset_class']
            # Use composite key to look up target percentage
            category_key = f"{asset_class_name}:{category_name}"
            target_pct = target_category_breakdown.get(category_key, 0)
            current_value = float(category_item['subtotal'])

            # Calculate target dollar amount
            target_dollar = (total_value_float * target_pct / 100) if target_pct > 0 else 0

            # Calculate difference (positive = under target, negative = over target)
            difference = target_dollar - current_value

            category_item['target_pct'] = round(target_pct, 2)
            # current_pct is already calculated above, no need to recalculate
            category_item['target_dollar'] = round(target_dollar, 2)
            category_item['difference'] = round(difference, 2)

    # Calculate retirement status display text
    retirement_status = None
    if years_to_retirement is not None:
        if years_to_retirement < 0:
            retirement_status = f"{abs(years_to_retirement)} years until retirement"
        elif years_to_retirement == 0:
            retirement_status = "Retirement this year!"
        else:
            retirement_status = f"{years_to_retirement} years past retirement"

    # Calculate rebalance recommendations if tolerance is provided
    rebalance_data = None

    return {
        'class_breakdown': {k: float(v) for k, v in class_breakdown.items()},
        'category_breakdown': {k: float(v) for k, v in category_breakdown.items()},
        'target_class_breakdown': target_class_breakdown,
        'target_category_breakdown': target_category_breakdown,
        'category_details': formatted_category_details,
        'total_value': float(total_value),
        'current_year': current_year,
        'year_born': portfolio.year_born,
        'retirement_age': portfolio.retirement_age,
        'years_to_retirement': years_to_retirement,
        'retirement_status': retirement_status,
        'rebalance_data': rebalance_data,
    }


def calculate_rebalance_recommendations(portfolio: Portfolio, tolerance: float) -> dict:
    """
    Calculate rebalance recommendations based on tolerance threshold with account-aware allocation.

    For Sells: Identifies which accounts to sell from (largest balance first) until target is met
    For Buys: After sells are determined, allocates available cash from smallest account to largest deficit

    Args:
        portfolio: Portfolio instance
        tolerance: Tolerance threshold as percentage (e.g., 2.0 for 2%)

    Returns:
        dict with:
        - recommendations: list of buy/sell actions with account allocations
        - total_buys: total dollar amount to buy
        - total_sells: total dollar amount to sell
        - net_balanced: whether sells and buys are balanced
    """
    # Get portfolio analysis data
    analysis_data = get_portfolio_analysis(portfolio)

    if not analysis_data.get('target_category_breakdown'):
        return {
            'recommendations': [],
            'total_buys': 0,
            'total_sells': 0,
            'net_balanced': True,
            'message': 'No glidepath rule assigned or retirement age not set'
        }

    total_value = analysis_data['total_value']
    if total_value <= 0:
        return {
            'recommendations': [],
            'total_buys': 0,
            'total_sells': 0,
            'net_balanced': True,
            'message': 'Portfolio has no value'
        }

    # Build list of all categories with their metrics
    all_categories = []
    any_category_exceeded = False

    for category_item in analysis_data['category_details']:
        category_name = category_item['category']
        asset_class = category_item['asset_class']
        actual_pct = category_item.get('current_pct', 0)
        target_pct = category_item.get('target_pct', 0)
        actual_dollar = category_item['subtotal']
        target_dollar = (total_value * target_pct / 100) if target_pct > 0 else 0

        # Calculate percentage difference (target - actual)
        pct_diff = target_pct - actual_pct
        dollar_diff = target_dollar - actual_dollar

        # Check if exceeds tolerance
        exceeds_tolerance = abs(pct_diff) > tolerance

        if exceeds_tolerance and category_name not in ['Other', 'Unknown']:
            any_category_exceeded = True

        all_categories.append({
            'category': category_name,
            'asset_class': asset_class,
            'actual_pct': actual_pct,
            'target_pct': target_pct,
            'actual_dollar': actual_dollar,
            'target_dollar': target_dollar,
            'pct_diff': pct_diff,
            'dollar_diff': dollar_diff,
            'exceeds_tolerance': exceeds_tolerance,
        })

    # Sort by pct_diff (low to high: most oversized to most undersized)
    all_categories.sort(key=lambda x: x['pct_diff'])

    # Identify categories to rebalance
    rebalance_categories = []

    for cat in all_categories:
        include = False

        if cat['category'] == 'Other':
            # Include Other if ANY category exceeded AND Other value > $1
            include = any_category_exceeded and cat['actual_dollar'] > 1
        elif cat['category'] == 'Unknown':
            # Include Unknown only if it exceeds tolerance
            include = cat['exceeds_tolerance']
        else:
            # Regular categories: include if exceeds tolerance
            include = cat['exceeds_tolerance']

        if include:
            rebalance_categories.append(cat)

    # Calculate recommendations from rebalance categories with account-aware allocation
    recommendations = []
    total_sells = 0
    total_buys = 0

    # Track available cash in each account from sells
    account_cash_available = {}

    # Process SELLS first to determine account allocations
    for cat in rebalance_categories:
        if cat['dollar_diff'] < 0:
            # Need to sell
            category_name = cat['category']
            asset_class_name = cat['asset_class']
            sell_amount_needed = abs(cat['dollar_diff'])

            # Find all accounts with holdings in this category
            account_holdings = {}  # account_number -> value
            category_funds = []

            for cat_detail in analysis_data['category_details']:
                if cat_detail['category'] == category_name and cat_detail['asset_class'] == asset_class_name:
                    symbols = cat_detail.get('symbols', [])
                    # Collect holdings by account
                    for symbol_item in symbols:
                        acct = symbol_item.get('account_number')
                        value = symbol_item.get('value', 0)
                        if acct not in account_holdings:
                            account_holdings[acct] = 0
                        account_holdings[acct] += value

                    # Get fund list (sorted worst to best for selling)
                    category_funds = sorted(
                        symbols,
                        key=lambda x: x.get('preference') if x.get('preference') is not None else 256,
                        reverse=True  # Highest preference first (256→1)
                    )
                    break

            # Sort accounts by balance (largest first)
            sorted_accounts = sorted(account_holdings.items(), key=lambda x: x[1], reverse=True)

            # Allocate sells from each account until we meet target
            account_allocations = []
            remaining_to_sell = sell_amount_needed

            for account_number, account_balance in sorted_accounts:
                if remaining_to_sell <= 0:
                    break

                # Sell only what's needed (partial sale allowed from last account)
                sell_from_account = min(remaining_to_sell, account_balance)
                account_allocations.append({
                    'account_number': account_number,
                    'amount': round(sell_from_account, 2)
                })

                # Track available cash for buying
                if account_number not in account_cash_available:
                    account_cash_available[account_number] = 0
                account_cash_available[account_number] += sell_from_account

                remaining_to_sell -= sell_from_account

            total_sells += sell_amount_needed
            recommendations.append({
                'action': 'Sell',
                'amount': round(sell_amount_needed, 2),
                'category': category_name,
                'asset_class': asset_class_name,
                'tagged': True,
                'account_allocations': account_allocations,
                'funds': category_funds
            })

    # Process BUYS with account-aware allocation
    buy_list = [cat for cat in rebalance_categories if cat['dollar_diff'] > 0]

    # Also add untagged categories that need balancing
    untagged_categories = [cat for cat in all_categories if cat not in rebalance_categories]

    # Balance net difference
    net = total_sells - total_buys
    if net > 0:
        # More sells than buys - add buy recommendations for untagged categories
        remaining = net
        for cat in reversed(untagged_categories):
            if remaining <= 0:
                break
            max_buy = cat['target_dollar'] - cat['actual_dollar']
            if max_buy > 0:
                buy_amount = min(remaining, max_buy)
                buy_list.append({
                    'category': cat['category'],
                    'asset_class': cat['asset_class'],
                    'dollar_diff': buy_amount,
                    'is_untagged': True
                })
                remaining -= buy_amount

    elif net < 0:
        # More buys than sells - add sell recommendations for untagged categories
        remaining = abs(net)
        for cat in untagged_categories:
            if remaining <= 0:
                break
            max_sell = cat['actual_dollar'] - cat['target_dollar']
            if max_sell > 0:
                sell_amount = min(remaining, max_sell)

                # Find funds in this category
                category_funds = []
                account_holdings = {}
                for cat_detail in analysis_data['category_details']:
                    if cat_detail['category'] == cat['category'] and cat_detail['asset_class'] == cat['asset_class']:
                        symbols = cat_detail.get('symbols', [])
                        for symbol_item in symbols:
                            acct = symbol_item.get('account_number')
                            value = symbol_item.get('value', 0)
                            if acct not in account_holdings:
                                account_holdings[acct] = 0
                            account_holdings[acct] += value

                        category_funds = sorted(symbols, key=lambda x: x.get('preference') if x.get('preference') is not None else 256, reverse=True)
                        break

                # Sort accounts by balance (largest first)
                sorted_accounts = sorted(account_holdings.items(), key=lambda x: x[1], reverse=True)

                # Allocate sells
                account_allocations = []
                remaining_to_sell = sell_amount
                for account_number, account_balance in sorted_accounts:
                    if remaining_to_sell <= 0:
                        break
                    sell_from_account = min(remaining_to_sell, account_balance)
                    account_allocations.append({
                        'account_number': account_number,
                        'amount': round(sell_from_account, 2)
                    })
                    if account_number not in account_cash_available:
                        account_cash_available[account_number] = 0
                    account_cash_available[account_number] += sell_from_account
                    remaining_to_sell -= sell_from_account

                total_sells += sell_amount
                recommendations.append({
                    'action': 'Sell',
                    'amount': round(sell_amount, 2),
                    'category': cat['category'],
                    'asset_class': cat['asset_class'],
                    'tagged': False,
                    'account_allocations': account_allocations,
                    'funds': category_funds
                })
                remaining -= sell_amount

    # Sort buy_list by deficit amount (largest first)
    buy_list.sort(key=lambda x: x['dollar_diff'], reverse=True)

    # Now allocate available cash to buys
    # Sort accounts by available cash (smallest first)
    sorted_accounts_by_cash = sorted(account_cash_available.items(), key=lambda x: x[1])

    for account_number, available_cash in sorted_accounts_by_cash:
        remaining_cash = available_cash

        # Apply this account's cash to buy categories (starting with largest deficit)
        for buy_cat in buy_list:
            if remaining_cash <= 0:
                break

            buy_amount = buy_cat['dollar_diff']
            # Check if this buy recommendation already exists
            existing_rec = next((r for r in recommendations if r['action'] == 'Buy' and
                               r['category'] == buy_cat['category'] and
                               r['asset_class'] == buy_cat['asset_class']), None)

            if existing_rec:
                # Add to existing recommendation
                if 'account_allocations' not in existing_rec:
                    existing_rec['account_allocations'] = []

                allocate_amount = min(remaining_cash, buy_amount)
                existing_rec['account_allocations'].append({
                    'account_number': account_number,
                    'amount': round(allocate_amount, 2)
                })
                remaining_cash -= allocate_amount
            else:
                # Create new buy recommendation
                allocate_amount = min(remaining_cash, buy_amount)

                # Get recommended funds
                recommended_funds = []
                try:
                    from .models import AssetCategory
                    asset_category = AssetCategory.objects.filter(
                        asset_class__name=buy_cat['asset_class'],
                        name=buy_cat['category']
                    ).prefetch_related('funds').first()

                    if asset_category:
                        recommended_funds = [
                            {
                                'ticker': fund.ticker,
                                'fund_name': fund.name,
                                'preference': fund.preference,
                                'is_recommended': True
                            }
                            for fund in asset_category.funds.filter(preference__gte=1, preference__lte=10).order_by('preference')
                        ]
                except:
                    pass

                recommendations.append({
                    'action': 'Buy',
                    'amount': round(buy_amount, 2),
                    'category': buy_cat['category'],
                    'asset_class': buy_cat['asset_class'],
                    'tagged': buy_cat.get('is_untagged', True),
                    'account_allocations': [{
                        'account_number': account_number,
                        'amount': round(allocate_amount, 2)
                    }],
                    'funds': recommended_funds
                })
                total_buys += buy_amount
                remaining_cash -= allocate_amount

    return {
        'recommendations': recommendations,
        'total_buys': total_buys,
        'total_sells': total_sells,
        'net_balanced': abs(total_sells - total_buys) < 0.01,
    }
