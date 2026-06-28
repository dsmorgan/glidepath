"""Deterministic education (529) balance projection.

Models a forward balance trajectory from today through the end of the college
withdrawal period, in two phases:

  Accumulation (year t < years_to_enrollment):
      balance[t+1] = balance[t] * (1 + r) + annual_contribution
  Withdrawal (years_to_enrollment <= t < years_to_enrollment + college_duration):
      balance[t+1] = balance[t] * (1 + r) - annual_withdrawal

`years_to_enrollment` may be negative (student already enrolled), in which case
the accumulation phase is empty and only the remaining school years are projected.

This is the deterministic analogue of monte_carlo.py for retirement; a probabilistic
education projection can be layered on later (spec section 12.4).
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from .account_services import get_portfolio_analysis


def _d(value) -> Decimal:
    """Coerce a value (None/float/str/Decimal) to Decimal, defaulting to 0."""
    if value is None or value == "":
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _project(current_balance: Decimal, years_to_enrollment: int, college_duration: int,
             annual_contribution: Decimal, annual_withdrawal: Decimal, rate: Decimal):
    """Run the year-by-year recurrence. Returns (boundary_balances, phases).

    boundary_balances has one more entry than phases: balances[i] is the balance at
    the start of step i, phases[i] is that step's phase ('accumulation'/'withdrawal').
    """
    total_steps = max(0, years_to_enrollment + college_duration)
    balances = [current_balance]
    phases = []
    balance = current_balance
    for i in range(total_steps):
        if i < years_to_enrollment:
            balance = balance * (Decimal("1") + rate) + annual_contribution
            phases.append("accumulation")
        else:
            balance = balance * (Decimal("1") + rate) - annual_withdrawal
            phases.append("withdrawal")
        balances.append(balance)
    return balances, phases


def calculate_required_contribution(current_balance, years_to_enrollment, college_duration,
                                    annual_withdrawal, return_assumption):
    """Back-solve the annual contribution that leaves a $0 balance at graduation.

    Returns a Decimal (>= 0), or None when contributions can't close the gap (no
    accumulation years remain, i.e. years_to_enrollment <= 0). The end balance is
    linear in the contribution, so two evaluations determine the required value.
    """
    current_balance = _d(current_balance)
    annual_withdrawal = _d(annual_withdrawal)
    rate = _d(return_assumption) / Decimal("100")
    college_duration = int(college_duration or 0)

    if years_to_enrollment is None or years_to_enrollment <= 0:
        return None

    def end_balance(contribution: Decimal) -> Decimal:
        balances, _ = _project(current_balance, years_to_enrollment, college_duration,
                               contribution, annual_withdrawal, rate)
        return balances[-1]

    e0 = end_balance(Decimal("0"))
    e1 = end_balance(Decimal("1"))
    slope = e1 - e0
    if slope == 0:
        return None
    required = -e0 / slope
    return required if required > 0 else Decimal("0")


def calculate_education_projection(portfolio) -> dict:
    """Year-by-year balance projection for an education portfolio.

    Returns a dict with the projection table and derived metrics, or
    {'available': False, 'missing': [...]} when required inputs are absent.
    """
    missing = []
    if portfolio.years_to_enrollment is None:
        missing.append("Years to Enrollment")
    if portfolio.return_assumption is None:
        missing.append("Return Assumption")
    if portfolio.annual_withdrawal is None:
        missing.append("Annual Withdrawal")
    if missing:
        return {"available": False, "missing": missing}

    analysis = get_portfolio_analysis(portfolio)
    current_balance = _d(analysis.get("total_value", 0))

    years_to_enrollment = int(portfolio.years_to_enrollment)
    college_duration = int(portfolio.college_duration_years or 4)
    annual_contribution = _d(portfolio.annual_contribution)
    annual_withdrawal = _d(portfolio.annual_withdrawal)
    rate = _d(portfolio.return_assumption) / Decimal("100")
    current_year = datetime.now().year

    balances, phases = _project(current_balance, years_to_enrollment, college_duration,
                                annual_contribution, annual_withdrawal, rate)

    rows = []
    for i, balance in enumerate(balances):
        if i == 0:
            phase = "current"
        else:
            phase = phases[i - 1]
        rows.append({
            "year_offset": i,
            "calendar_year": current_year + i,
            "phase": phase,
            "balance": _money(balance),
        })

    # Enrollment-boundary balance (only meaningful if enrollment is still ahead).
    projected_at_enrollment = None
    if 0 <= years_to_enrollment < len(balances):
        projected_at_enrollment = _money(balances[years_to_enrollment])

    projected_at_graduation = _money(balances[-1]) if balances else _money(current_balance)
    total_withdrawals = annual_withdrawal * Decimal(college_duration)
    shortfall = any(b < 0 for b in balances)
    funding_gap = _money(-balances[-1]) if balances and balances[-1] < 0 else 0.0

    required = calculate_required_contribution(
        current_balance, years_to_enrollment, college_duration,
        annual_withdrawal, portfolio.return_assumption,
    )

    return {
        "available": True,
        "current_balance": _money(current_balance),
        "years": [r["calendar_year"] for r in rows],
        "balances": [r["balance"] for r in rows],
        "rows": rows,
        "projected_balance_at_enrollment": projected_at_enrollment,
        "projected_balance_at_graduation": projected_at_graduation,
        "total_withdrawals": _money(total_withdrawals),
        "funding_gap": funding_gap,
        "shortfall": shortfall,
        "required_annual_contribution": (_money(required) if required is not None else None),
        "years_to_enrollment": years_to_enrollment,
        "college_duration_years": college_duration,
    }
