"""
Monte Carlo Retirement Simulation Service

This module provides retirement projection modeling using Monte Carlo simulation.
It simulates portfolio growth and drawdown based on:
- User's current portfolio balance and allocation
- Glidepath rules (dynamic asset allocation by age)
- Contribution and withdrawal patterns
- Stochastic returns based on historical asset class statistics
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


def run_monte_carlo_simulation(
    portfolio,
    annual_contribution,
    withdrawal_mode,
    withdrawal_amount,
    inflation_rate=0.03,
    num_simulations=1000,
    end_age=95
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
            rules_by_age=rules_by_age
        )
        all_paths.append(path)

        # Check if this run was successful (never hit $0)
        if all(balance > 0 for _, balance in path):
            successful_runs += 1

    # Calculate percentiles
    percentile_10 = _calculate_percentile_path(all_paths, 10)
    percentile_50 = _calculate_percentile_path(all_paths, 50)
    percentile_90 = _calculate_percentile_path(all_paths, 90)

    # Calculate expected balances at key milestones
    retirement_balances = [path[years_to_retirement][1] for path in all_paths]
    end_balances = [path[-1][1] for path in all_paths]

    return {
        'percentile_10': percentile_10,
        'percentile_50': percentile_50,
        'percentile_90': percentile_90,
        'probability_of_success': (successful_runs / num_simulations) * 100,
        'expected_balance_at_retirement': np.median(retirement_balances),
        'expected_balance_at_end': np.median(end_balances),
        'starting_balance': starting_balance,
        'current_age': current_age,
        'retirement_age': retirement_age,
        'upload_date': upload_date,
        'days_since_upload': days_since_upload
    }


def _get_rules_by_retirement_age(ruleset):
    """
    Extract glidepath rules and create a lookup by retirement age.

    Returns:
        dict mapping retirement_age -> allocation percentages by asset class
    """
    from .models import GlidepathRule

    rules = GlidepathRule.objects.filter(ruleset=ruleset).prefetch_related('class_allocations__asset_class')

    rules_by_age = {}
    for rule in rules:
        # For each age in the band, store the allocation
        for age in range(rule.gt_retire_age, rule.lt_retire_age + 1):
            allocation = {}
            for class_alloc in rule.class_allocations.all():
                allocation[class_alloc.asset_class.name] = float(class_alloc.percentage) / 100.0
            rules_by_age[age] = allocation

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
    rules_by_age
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

    for age in range(current_age + 1, end_age + 1):
        years_from_retirement = age - retirement_age

        # Get target allocation from glidepath
        allocation = rules_by_age.get(years_from_retirement, {})

        # Sample returns for this year based on allocation
        portfolio_return = _sample_portfolio_return(allocation)

        # Apply return to balance
        balance = balance * (1 + portfolio_return)

        # Handle contributions (pre-retirement) or withdrawals (post-retirement)
        if age < retirement_age:
            # Add annual contribution
            balance += annual_contribution
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


def _sample_portfolio_return(allocation):
    """
    Sample a single year's return based on portfolio allocation.

    Assumes returns are normally distributed and independent across asset classes.

    Args:
        allocation: dict mapping asset class name -> percentage (as decimal)

    Returns:
        float: portfolio return for the year
    """
    portfolio_return = 0.0

    for asset_class, weight in allocation.items():
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
