"""Everyday-life calculator tools for finance, health, and time."""

import calendar
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool


def _to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value.strip())


@tool
def calculate_loan_payment(
    principal: float,
    annual_rate_percent: float,
    years: float,
) -> str:
    """Estimate the monthly payment and total interest of a fixed-rate loan.

    Use for mortgages, car loans, or personal loans. The rate is the annual
    percentage rate (for example 6.5 for 6.5%).
    """
    if principal <= 0 or years <= 0 or annual_rate_percent < 0:
        return (
            "Error: principal and years must be positive and the rate cannot "
            "be negative."
        )

    months = int(round(years * 12))
    if months < 1:
        return "Error: loan term must be at least one month."

    monthly_rate = annual_rate_percent / 100 / 12

    if monthly_rate == 0:
        payment = principal / months
    else:
        factor = (1 + monthly_rate) ** months
        payment = principal * monthly_rate * factor / (factor - 1)

    total_paid = payment * months

    return _to_json(
        {
            "principal": round(principal, 2),
            "annual_rate_percent": annual_rate_percent,
            "years": years,
            "monthly_payment": round(payment, 2),
            "total_paid": round(total_paid, 2),
            "total_interest": round(total_paid - principal, 2),
        }
    )


@tool
def calculate_tip_split(
    bill_amount: float,
    tip_percent: float = 15.0,
    split_ways: int = 1,
) -> str:
    """Calculate a tip, the total bill, and the amount per person."""
    if bill_amount < 0:
        return "Error: bill_amount cannot be negative."
    if tip_percent < 0:
        return "Error: tip_percent cannot be negative."
    if split_ways < 1:
        return "Error: split_ways must be at least 1."

    tip = bill_amount * tip_percent / 100
    total = bill_amount + tip
    per_person = total / split_ways

    return _to_json(
        {
            "bill_amount": round(bill_amount, 2),
            "tip_percent": tip_percent,
            "tip": round(tip, 2),
            "total": round(total, 2),
            "split_ways": split_ways,
            "per_person": round(per_person, 2),
        }
    )


@tool
def calculate_bmi(weight_kg: float, height_m: float) -> str:
    """Calculate body mass index (BMI) and its standard category."""
    if weight_kg <= 0 or height_m <= 0:
        return "Error: weight and height must be positive."

    bmi = weight_kg / (height_m**2)

    if bmi < 18.5:
        category = "underweight"
    elif bmi < 25:
        category = "normal"
    elif bmi < 30:
        category = "overweight"
    else:
        category = "obese"

    return _to_json(
        {
            "weight_kg": weight_kg,
            "height_m": height_m,
            "bmi": round(bmi, 2),
            "category": category,
        }
    )


@tool
def calculate_age(birth_date: str, on_date: str | None = None) -> str:
    """Calculate age in years, months, and days from a YYYY-MM-DD birth date.

    Pass on_date to measure age at a specific date; defaults to today.
    """
    try:
        birth = _parse_date(birth_date)
        current = _parse_date(on_date) if on_date else date.today()
    except ValueError:
        return "Error: dates must use YYYY-MM-DD format."

    if birth > current:
        return "Error: birth_date cannot be after on_date."

    years = current.year - birth.year
    months = current.month - birth.month
    days = current.day - birth.day

    if days < 0:
        months -= 1
        previous_year = current.year if current.month > 1 else current.year - 1
        previous_month = current.month - 1 if current.month > 1 else 12
        days += calendar.monthrange(previous_year, previous_month)[1]

    if months < 0:
        years -= 1
        months += 12

    return _to_json(
        {
            "birth_date": birth.isoformat(),
            "on_date": current.isoformat(),
            "age_years": years,
            "age_months": months,
            "age_days": days,
            "total_days": (current - birth).days,
        }
    )


@tool
def days_between(start_date: str, end_date: str) -> str:
    """Count the days and weekdays between two YYYY-MM-DD dates."""
    try:
        start = _parse_date(start_date)
        end = _parse_date(end_date)
    except ValueError:
        return "Error: dates must use YYYY-MM-DD format."

    total_days = (end - start).days
    if abs(total_days) > 36500:
        return "Error: date range must be within 100 years."

    ordered_start, ordered_end = sorted((start, end))
    business_days = 0
    cursor = ordered_start

    while cursor < ordered_end:
        if cursor.weekday() < 5:
            business_days += 1
        cursor = date.fromordinal(cursor.toordinal() + 1)

    return _to_json(
        {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "days": total_days,
            "weeks": round(abs(total_days) / 7, 2),
            "business_days": business_days,
            "weekend_days": abs(total_days) - business_days,
        }
    )


@tool
def convert_timezone(
    date_time: str,
    from_timezone: str,
    to_timezone: str,
) -> str:
    """Convert an ISO 8601 date-time between IANA timezones.

    Example: convert_timezone("2026-11-09T12:00:00", "UTC", "Asia/Dhaka").
    """
    try:
        moment = datetime.fromisoformat(date_time.strip())
    except ValueError:
        return "Error: date_time must be ISO 8601, for example 2026-11-09T12:00:00."

    try:
        source = ZoneInfo(from_timezone.strip())
        target = ZoneInfo(to_timezone.strip())
    except ZoneInfoNotFoundError as error:
        return f"Error: {error}"

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=source)
    else:
        moment = moment.astimezone(source)

    converted = moment.astimezone(target)

    return _to_json(
        {
            "input": moment.isoformat(),
            "from_timezone": from_timezone,
            "to_timezone": to_timezone,
            "converted": converted.isoformat(),
            "utc_offset": converted.strftime("%z"),
        }
    )


@tool
def estimate_fuel_cost(
    distance_km: float,
    fuel_efficiency_l_per_100km: float,
    fuel_price_per_liter: float,
) -> str:
    """Estimate fuel needed and total fuel cost for a trip."""
    if distance_km < 0 or fuel_efficiency_l_per_100km <= 0:
        return "Error: distance must be non-negative and efficiency positive."
    if fuel_price_per_liter < 0:
        return "Error: fuel price cannot be negative."

    liters = distance_km / 100 * fuel_efficiency_l_per_100km
    cost = liters * fuel_price_per_liter

    return _to_json(
        {
            "distance_km": distance_km,
            "fuel_efficiency_l_per_100km": fuel_efficiency_l_per_100km,
            "fuel_price_per_liter": fuel_price_per_liter,
            "liters_needed": round(liters, 2),
            "total_cost": round(cost, 2),
        }
    )
