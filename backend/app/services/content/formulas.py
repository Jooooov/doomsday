"""
Deterministic quantity calculation formulas.
All quantities are calculated from user profile variables — no LLM needed.
"""
import re
from typing import Optional


def calculate_water_liters(household_size: int, days: int = 3) -> float:
    """4L per person per day (drinking + sanitation minimum)."""
    return 4.0 * household_size * days


def calculate_food_calories(household_size: int, days: int = 3) -> float:
    """2000 kcal per person per day baseline."""
    return 2000.0 * household_size * days


def calculate_water_purification_tablets(household_size: int, days: int = 14) -> int:
    """1 tablet per 2L, 2L/person/day for drinking only."""
    return int(2.0 * household_size * days)


def calculate_first_aid_kits(household_size: int) -> int:
    """1 kit per 4 people, minimum 1."""
    return max(1, -(-household_size // 4))  # ceiling division


def calculate_fuel_liters(has_vehicle: bool, evacuation_distance_km: float = 200) -> float:
    """200km evacuation + 20% reserve at 10L/100km."""
    if not has_vehicle:
        return 0.0
    return (evacuation_distance_km / 100 * 10) * 1.2


def calculate_food_days(household_size: int, days: int = 3) -> dict:
    """Return food quantities broken down by type."""
    return {
        "canned_goods_kg": round(0.5 * household_size * days, 1),
        "rice_or_pasta_kg": round(0.3 * household_size * days, 1),
        "protein_cans": int(0.5 * household_size * days),
    }


def evaluate_formula(formula: str, variables: dict) -> Optional[float]:
    """
    Safely evaluate a deterministic formula string with user-supplied variables.
    Only arithmetic (+, -, *, /) and parentheses allowed.
    """
    try:
        expr = formula
        # Replace variable names with their numeric values (longest first to avoid partial matches)
        for var, val in sorted(variables.items(), key=lambda x: -len(x[0])):
            expr = expr.replace(var, str(float(val)))

        # Safety: only allow digits, operators, and whitespace
        cleaned = re.sub(r"\s+", " ", expr).strip()
        if not re.match(r"^[\d\s\.\+\-\*\/\(\)]+$", cleaned):
            return None

        return float(eval(cleaned))  # noqa: S307 — safe after whitelist check
    except Exception:
        return None


def apply_profile_to_checklist_item(item: dict, household_size: int, has_vehicle: bool) -> dict:
    """Compute calculated_quantity from formula + profile variables."""
    formula = item.get("formula")
    if not formula:
        return item

    variables = {
        "household_size": household_size,
        "num_people": household_size,
        "has_vehicle": 1 if has_vehicle else 0,
        "days": 3,
    }
    result = evaluate_formula(formula, variables)
    if result is not None:
        item["calculated_quantity"] = round(result, 2)
    return item
