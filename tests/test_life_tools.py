import json

from agentic_chatbot.tools.life import (
    calculate_age,
    calculate_bmi,
    calculate_loan_payment,
    calculate_tip_split,
    convert_timezone,
    days_between,
    estimate_fuel_cost,
)


def test_loan_payment_matches_standard_amortization():
    payload = json.loads(
        calculate_loan_payment.invoke(
            {
                "principal": 100000,
                "annual_rate_percent": 6,
                "years": 30,
            }
        )
    )

    assert payload["monthly_payment"] == 599.55
    assert payload["total_paid"] == 215838.19
    assert payload["total_interest"] == 115838.19


def test_loan_payment_rejects_invalid_input():
    assert calculate_loan_payment.invoke(
        {"principal": 0, "annual_rate_percent": 6, "years": 30}
    ).startswith("Error:")


def test_tip_split_calculates_per_person_amount():
    payload = json.loads(
        calculate_tip_split.invoke(
            {"bill_amount": 100, "tip_percent": 15, "split_ways": 2}
        )
    )

    assert payload["tip"] == 15.0
    assert payload["total"] == 115.0
    assert payload["per_person"] == 57.5


def test_bmi_category():
    payload = json.loads(
        calculate_bmi.invoke({"weight_kg": 70, "height_m": 1.75})
    )

    assert payload["bmi"] == 22.86
    assert payload["category"] == "normal"


def test_age_calculation_on_fixed_date():
    payload = json.loads(
        calculate_age.invoke(
            {"birth_date": "1990-05-10", "on_date": "2026-11-09"}
        )
    )

    assert payload["age_years"] == 36
    assert payload["age_months"] == 5
    assert payload["age_days"] == 30


def test_age_rejects_future_birth_date():
    assert calculate_age.invoke(
        {"birth_date": "2030-01-01", "on_date": "2026-11-09"}
    ).startswith("Error:")


def test_days_between_counts_weekdays():
    payload = json.loads(
        days_between.invoke(
            {"start_date": "2026-11-01", "end_date": "2026-11-09"}
        )
    )

    assert payload["days"] == 8
    assert payload["business_days"] == 5


def test_days_between_rejects_bad_format():
    assert days_between.invoke(
        {"start_date": "11/01/2026", "end_date": "2026-11-09"}
    ).startswith("Error:")


def test_convert_timezone_utc_to_dhaka():
    payload = json.loads(
        convert_timezone.invoke(
            {
                "date_time": "2026-11-09T12:00:00",
                "from_timezone": "UTC",
                "to_timezone": "Asia/Dhaka",
            }
        )
    )

    assert payload["converted"] == "2026-11-09T18:00:00+06:00"


def test_convert_timezone_rejects_unknown_zone():
    assert convert_timezone.invoke(
        {
            "date_time": "2026-11-09T12:00:00",
            "from_timezone": "UTC",
            "to_timezone": "Mars/Olympus",
        }
    ).startswith("Error:")


def test_estimate_fuel_cost():
    payload = json.loads(
        estimate_fuel_cost.invoke(
            {
                "distance_km": 100,
                "fuel_efficiency_l_per_100km": 5,
                "fuel_price_per_liter": 2,
            }
        )
    )

    assert payload["liters_needed"] == 5.0
    assert payload["total_cost"] == 10.0
