"""
Monte Carlo Retirement Simulation Service

This module provides retirement projection modeling using Monte Carlo simulation.
It simulates portfolio growth and drawdown based on:
- User's current portfolio balance and allocation
- Glidepath rules (dynamic asset allocation by age)
- Contribution and withdrawal patterns
- Stochastic returns based on historical asset class statistics or custom mappings
"""

import numpy as np
from decimal import Decimal
from django.utils import timezone


# Hard-coded asset class return assumptions
# These are based on historical long-term averages and should be reviewed periodically
ASSET_CLASS_ASSUMPTIONS = {
    'Stocks': {
        'mean_return': 0.10,      # 10% annual return
        'std_dev': 0.18,          # 18% standard deviation
        'description': 'Based on historical S&P 500 returns (1926-2024, including dividends)'
    },
    'Bonds': {
        'mean_return': 0.04,      # 4% annual return
        'std_dev': 0.06,          # 6% standard deviation
        'description': 'Based on intermediate-term government bonds (10-year Treasury)'
    },
    'Crypto': {
        'mean_return': 0.15,      # 15% annual return (conservative for crypto)
        'std_dev': 0.60,          # 60% standard deviation (high volatility)
        'description': 'Highly speculative - based on limited Bitcoin history (2013-2024)'
    },
    'Other': {
        'mean_return': 0.03,      # 3% annual return
        'std_dev': 0.05,          # 5% standard deviation
        'description': 'Cash equivalents, money market funds, and other low-risk assets'
    }
}


def get_category_assumptions(category):
    """
    Get mean return and standard deviation for a category.

    Uses custom mapping if available, otherwise falls back to asset class defaults.

    Args:
        category: AssetCategory instance

    Returns:
        tuple: (mean_return, std_dev) as floats (e.g., 0.10 for 10%)
    """
    from .models import CategoryAssumptionMapping

    try:
        mapping = CategoryAssumptionMapping.objects.get(category=category)
        mean_return = mapping.get_mean_return()
        std_dev = mapping.get_std_dev()

        if mean_return is not None and std_dev is not None:
            return (float(mean_return), float(std_dev))
    except CategoryAssumptionMapping.DoesNotExist:
        pass

    # Fall back to asset class defaults
    class_name = category.asset_class.name
    if class_name in ASSET_CLASS_ASSUMPTIONS:
        assumptions = ASSET_CLASS_ASSUMPTIONS[class_name]
        return (assumptions['mean_return'], assumptions['std_dev'])

    # Ultimate fallback (should not happen)
    return (0.05, 0.10)


def run_monte_carlo_simulation(
    portfolio,
    annual_contribution,
    withdrawal_mode,
    withdrawal_amount,
    inflation_rate=0.03,
    num_simulations=1000,
    end_age=95,
    pessimistic_percentile=30,
    optimistic_percentile=70
):
    """
    Run Monte Carlo simulation for retirement planning.

    Args:
        portfolio: Portfolio model instance
        annual_contribution: Decimal, annual contribution until retirement
        withdrawal_mode: 'percent' or 'dollar'
        withdrawal_amount: float, either percentage (e.g., 4.0 for 4%) or dollar amount
        inflation_rate: float, annual inflation rate (default 0.03 for 3%)
        num_simulations: int, number of Monte Carlo runs (default 1000)
        end_age: int, age to simulate until (default 95)
        pessimistic_percentile: int, lower percentile for chart (default 30)
        optimistic_percentile: int, upper percentile for chart (default 70)

    Returns:
        dict with simulation results including percentile paths and metrics
    """
    from .account_services import get_portfolio_analysis

    # Get current portfolio state
    analysis = get_portfolio_analysis(portfolio)
    starting_balance = float(analysis.get('total_value', 0))
    current_allocation = analysis.get('allocation', {})

    # Calculate age information
    current_age = portfolio.get_current_age()
    retirement_age = portfolio.retirement_age
    years_to_retirement = retirement_age - current_age

    # Get most recent upload date
    from .models import AccountUpload
    # Get account numbers from portfolio items
    account_numbers = portfolio.items.values_list('account_number', flat=True).distinct()

    # Find most recent upload for any of these accounts
    latest_upload = AccountUpload.objects.filter(
        user=portfolio.user,
        positions__account_number__in=account_numbers
    ).order_by('-upload_datetime').first()

    upload_date = latest_upload.upload_datetime if latest_upload else None
    days_since_upload = (timezone.now() - upload_date).days if upload_date else None

    # Calculate inflation-adjusted withdrawal amount for dollar mode
    if withdrawal_mode == 'dollar':
        # Project forward to retirement with inflation
        base_withdrawal_amount = withdrawal_amount * ((1 + inflation_rate) ** years_to_retirement)
    else:
        # For percent mode, we'll calculate based on retirement balance
        withdrawal_percentage = withdrawal_amount / 100.0
        base_withdrawal_amount = None  # Will be calculated at retirement

    # Get glidepath rules
    ruleset = portfolio.ruleset
    rules_by_age = _get_rules_by_retirement_age(ruleset)

    # PRE-LOAD all category assumptions to avoid database queries in simulation loop
    category_assumptions_cache = _build_category_assumptions_cache(rules_by_age)

    # Run simulations
    all_paths = []
    successful_runs = 0

    for sim in range(num_simulations):
        path = _run_single_simulation(
            starting_balance=starting_balance,
            current_age=current_age,
            retirement_age=retirement_age,
            end_age=end_age,
            annual_contribution=float(annual_contribution),
            withdrawal_mode=withdrawal_mode,
            base_withdrawal_amount=base_withdrawal_amount,
            withdrawal_percentage=withdrawal_percentage if withdrawal_mode == 'percent' else None,
            inflation_rate=inflation_rate,
            rules_by_age=rules_by_age,
            category_assumptions_cache=category_assumptions_cache
        )
        all_paths.append(path)

        # Check if this run was successful (never hit $0)
        if all(balance > 0 for _, balance in path):
            successful_runs += 1

    # Calculate percentiles
    percentile_pessimistic = _calculate_percentile_path(all_paths, pessimistic_percentile)
    percentile_50 = _calculate_percentile_path(all_paths, 50)
    percentile_optimistic = _calculate_percentile_path(all_paths, optimistic_percentile)

    # Calculate expected balances at key milestones
    retirement_balances = [path[years_to_retirement][1] for path in all_paths]
    end_balances = [path[-1][1] for path in all_paths]

    # Calculate total additional contributions (sum of all inflation-adjusted contributions until retirement)
    # This is a geometric series: contribution * sum((1+inflation)^i for i in 0..years-1)
    # Formula: contribution * ((1+r)^n - 1) / r
    if inflation_rate > 0 and years_to_retirement > 0:
        total_additional_contributions = float(annual_contribution) * (
            ((1 + inflation_rate) ** years_to_retirement - 1) / inflation_rate
        )
    elif years_to_retirement > 0:
        # If inflation is 0, just multiply
        total_additional_contributions = float(annual_contribution) * years_to_retirement
    else:
        total_additional_contributions = 0

    # Calculate inflation-adjusted annual withdrawal at retirement
    median_retirement_balance = np.median(retirement_balances)
    if withdrawal_mode == 'dollar':
        # Already calculated as base_withdrawal_amount
        annual_withdrawal_at_retirement = base_withdrawal_amount
    else:
        # Percentage mode: calculate based on median retirement balance
        annual_withdrawal_at_retirement = median_retirement_balance * withdrawal_percentage

    return {
        'percentile_pessimistic': percentile_pessimistic,
        'percentile_50': percentile_50,
        'percentile_optimistic': percentile_optimistic,
        'probability_of_success': (successful_runs / num_simulations) * 100,
        'expected_balance_at_retirement': median_retirement_balance,
        'expected_balance_at_end': np.median(end_balances),
        'starting_balance': starting_balance,
        'current_age': current_age,
        'retirement_age': retirement_age,
        'upload_date': upload_date,
        'days_since_upload': days_since_upload,
        'total_additional_contributions': total_additional_contributions,
        'annual_withdrawal_at_retirement': annual_withdrawal_at_retirement
    }


def _build_category_assumptions_cache(rules_by_age):
    """
    Build a cache of all category assumptions to avoid database queries during simulation.

    Args:
        rules_by_age: dict from _get_rules_by_retirement_age()

    Returns:
        dict mapping category.id -> (mean_return, std_dev)
    """
    from .models import CategoryAssumptionMapping

    cache = {}

    # Collect all unique categories from rules
    unique_categories = set()
    for age_data in rules_by_age.values():
        for (class_name, category) in age_data.get('categories', {}).keys():
            unique_categories.add(category)

    # Pre-fetch all mappings for these categories in a single query
    if unique_categories:
        category_ids = [cat.id for cat in unique_categories]
        mappings = CategoryAssumptionMapping.objects.filter(
            category_id__in=category_ids
        ).select_related('assumption_data', 'category__asset_class')

        # Build mapping dict
        mapping_dict = {mapping.category.id: mapping for mapping in mappings}

        # Build cache for each category
        for category in unique_categories:
            if category.id in mapping_dict:
                mapping = mapping_dict[category.id]
                mean_return = mapping.get_mean_return()
                std_dev = mapping.get_std_dev()

                if mean_return is not None and std_dev is not None:
                    cache[category.id] = (float(mean_return), float(std_dev))
                else:
                    # Fall back to class defaults
                    class_name = category.asset_class.name
                    if class_name in ASSET_CLASS_ASSUMPTIONS:
                        assumptions = ASSET_CLASS_ASSUMPTIONS[class_name]
                        cache[category.id] = (assumptions['mean_return'], assumptions['std_dev'])
                    else:
                        cache[category.id] = (0.05, 0.10)
            else:
                # No mapping exists, use class defaults
                class_name = category.asset_class.name
                if class_name in ASSET_CLASS_ASSUMPTIONS:
                    assumptions = ASSET_CLASS_ASSUMPTIONS[class_name]
                    cache[category.id] = (assumptions['mean_return'], assumptions['std_dev'])
                else:
                    cache[category.id] = (0.05, 0.10)

    return cache


def _get_rules_by_retirement_age(ruleset):
    """
    Extract glidepath rules and create a lookup by retirement age.

    Returns:
        dict mapping retirement_age -> allocation dict with:
            - 'class': dict of class_name -> percentage
            - 'categories': dict of (class_name, category_obj) -> percentage
    """
    from .models import GlidepathRule

    rules = GlidepathRule.objects.filter(ruleset=ruleset).prefetch_related(
        'class_allocations__asset_class',
        'category_allocations__asset_category__asset_class'
    )

    rules_by_age = {}
    for rule in rules:
        # For each age in the band, store the allocation
        for age in range(rule.gt_retire_age, rule.lt_retire_age + 1):
            # Class-level allocations
            class_allocation = {}
            for class_alloc in rule.class_allocations.all():
                class_allocation[class_alloc.asset_class.name] = float(class_alloc.percentage) / 100.0

            # Category-level allocations
            category_allocation = {}
            for cat_alloc in rule.category_allocations.all():
                class_name = cat_alloc.asset_category.asset_class.name
                category_allocation[(class_name, cat_alloc.asset_category)] = float(cat_alloc.percentage) / 100.0

            rules_by_age[age] = {
                'class': class_allocation,
                'categories': category_allocation
            }

    return rules_by_age


def _run_single_simulation(
    starting_balance,
    current_age,
    retirement_age,
    end_age,
    annual_contribution,
    withdrawal_mode,
    base_withdrawal_amount,
    withdrawal_percentage,
    inflation_rate,
    rules_by_age,
    category_assumptions_cache
):
    """
    Run a single Monte Carlo simulation path.

    Returns:
        list of (age, balance) tuples
    """
    balance = starting_balance
    path = [(current_age, balance)]

    # Track the withdrawal amount (for inflation adjustment)
    current_withdrawal = base_withdrawal_amount

    # Track the contribution amount (for inflation adjustment)
    current_contribution = annual_contribution

    for age in range(current_age + 1, end_age + 1):
        years_from_retirement = age - retirement_age

        # Get target allocation from glidepath
        allocation = rules_by_age.get(years_from_retirement, {})

        # Sample returns for this year based on allocation
        portfolio_return = _sample_portfolio_return(allocation, category_assumptions_cache)

        # Apply return to balance
        balance = balance * (1 + portfolio_return)

        # Handle contributions (pre-retirement) or withdrawals (post-retirement)
        if age < retirement_age:
            # Add annual contribution (inflation-adjusted)
            balance += current_contribution
            # Inflate contribution for next year
            current_contribution = current_contribution * (1 + inflation_rate)
        elif age >= retirement_age:
            # Calculate withdrawal amount
            if withdrawal_mode == 'percent':
                # First year of retirement: calculate based on balance
                if age == retirement_age:
                    current_withdrawal = balance * withdrawal_percentage
                else:
                    # Subsequent years: inflate previous withdrawal
                    current_withdrawal = current_withdrawal * (1 + inflation_rate)
            else:
                # Dollar mode: already inflation-adjusted to retirement, now continue inflating
                if age > retirement_age:
                    current_withdrawal = current_withdrawal * (1 + inflation_rate)

            # Subtract withdrawal
            balance -= current_withdrawal

            # Ensure balance doesn't go negative
            balance = max(0, balance)

        path.append((age, balance))

    return path


def _sample_portfolio_return(allocation, category_assumptions_cache):
    """
    Sample a single year's return based on portfolio allocation.

    Assumes returns are normally distributed and independent across asset classes/categories.

    Args:
        allocation: dict with:
            - 'class': dict mapping class_name -> percentage (as decimal)
            - 'categories': dict mapping (class_name, category_obj) -> percentage
        category_assumptions_cache: dict mapping category.id -> (mean_return, std_dev)

    Returns:
        float: portfolio return for the year
    """
    portfolio_return = 0.0

    # Check if we have category-level allocations
    categories = allocation.get('categories', {})
    class_allocation = allocation.get('class', {})

    if categories:
        # Use category-level allocations with cached assumptions
        for (class_name, category), weight in categories.items():
            # Look up cached assumptions (no database query!)
            if category.id in category_assumptions_cache:
                mean_return, std_dev = category_assumptions_cache[category.id]
            else:
                # Fallback if not in cache (shouldn't happen)
                if class_name in ASSET_CLASS_ASSUMPTIONS:
                    assumptions = ASSET_CLASS_ASSUMPTIONS[class_name]
                    mean_return = assumptions['mean_return']
                    std_dev = assumptions['std_dev']
                else:
                    mean_return = 0.05
                    std_dev = 0.10

            # Sample from normal distribution
            category_return = np.random.normal(mean_return, std_dev)
            portfolio_return += weight * category_return
    else:
        # Use class-level allocations with default assumptions
        for asset_class, weight in class_allocation.items():
            if asset_class in ASSET_CLASS_ASSUMPTIONS:
                assumptions = ASSET_CLASS_ASSUMPTIONS[asset_class]
                # Sample from normal distribution
                class_return = np.random.normal(
                    assumptions['mean_return'],
                    assumptions['std_dev']
                )
                portfolio_return += weight * class_return

    return portfolio_return


def _calculate_percentile_path(all_paths, percentile):
    """
    Calculate a specific percentile path across all simulations.

    Args:
        all_paths: list of paths, where each path is [(age, balance), ...]
        percentile: int, percentile to calculate (e.g., 10, 50, 90)

    Returns:
        list of (age, balance) tuples representing the percentile path
    """
    # Get the number of time steps (should be same for all paths)
    num_steps = len(all_paths[0])

    percentile_path = []
    for step in range(num_steps):
        age = all_paths[0][step][0]
        balances_at_step = [path[step][1] for path in all_paths]
        percentile_balance = np.percentile(balances_at_step, percentile)
        percentile_path.append((age, percentile_balance))

    return percentile_path
