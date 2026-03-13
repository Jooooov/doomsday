"""
Sanitation & Hygiene supply formula — deterministic, pure functions only.

Baselines:
  - FEMA / Red Cross hygiene guidelines
  - WHO WASH (Water, Sanitation & Hygiene) standards
  - Standard household consumption research

No LLM.  No randomness.  Same inputs → same outputs, always.
"""

from __future__ import annotations

import math

from .models import (
    CategoryResult,
    ResourceItem,
    VariableMap,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Toilet paper: 1 roll per person per 7 days (conservative; some cultures use more)
_TP_ROLLS_PER_PERSON_WEEK = 1.0

# Soap: 1 bar per standard-person per 14 days
_SOAP_BARS_PER_STD_PERSON_FORTNIGHT = 1.0

# Hand sanitiser: 30 ml/person/day  (WHO: 6 uses × 5 ml)
_HAND_SANITISER_ML_PER_PERSON_DAY = 30.0

# Garbage bags: 2 large bags per household per week
_GARBAGE_BAGS_PER_HOUSEHOLD_WEEK = 2

# Bleach (5% sodium hypochlorite): ~200 ml per std-person per week for surfaces
# Same bleach can disinfect ~15 L water per ml at 2 drops/L  → stores doubly useful
_BLEACH_L_PER_STD_PERSON_WEEK = 0.2

# Diapers: 8 per infant per day (WHO / UNICEF baseline for infants < 2 years)
_DIAPERS_PER_INFANT_DAY = 8

# Baby wipes: 1 pack (80 wipes) per infant per 10 days
_BABY_WIPE_PACK_DAYS = 10
_BABY_WIPES_PER_PACK = 80


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_sanitation(vm: VariableMap) -> CategoryResult:
    """
    Returns the sanitation category result for the given variable map.

    Pure function: deterministic, no side-effects, no I/O.
    """
    days          = vm.duration_days
    total_humans  = vm.total_humans
    std_persons   = vm.total_standard_persons
    weeks         = days / 7.0          # fractional weeks for proportional items

    # ---- Toilet paper ----
    toilet_paper_rolls = math.ceil(total_humans * _TP_ROLLS_PER_PERSON_WEEK * weeks)

    # ---- Soap ----
    soap_bars = math.ceil(std_persons * _SOAP_BARS_PER_STD_PERSON_FORTNIGHT * days / 14.0)

    # ---- Hand sanitiser ----
    hand_sanitiser_ml = math.ceil(total_humans * _HAND_SANITISER_ML_PER_PERSON_DAY * days)

    # ---- Garbage bags ----
    garbage_bags = math.ceil(_GARBAGE_BAGS_PER_HOUSEHOLD_WEEK * weeks)

    # ---- Bleach ----
    bleach_l = round(std_persons * _BLEACH_L_PER_STD_PERSON_WEEK * weeks, 2)
    bleach_l = max(0.25, bleach_l)          # minimum 250 ml

    # ---- Diapers (infants only) ----
    diapers = vm.infants_count * _DIAPERS_PER_INFANT_DAY * days

    # ---- Baby wipes ----
    baby_wipes = math.ceil(vm.infants_count * days / _BABY_WIPE_PACK_DAYS) * _BABY_WIPES_PER_PACK

    # ---- Build items ----
    items = [
        ResourceItem(
            name="Toilet paper rolls",
            quantity=float(toilet_paper_rolls),
            unit="rolls",
            notes="Store in dry location; double-layer rolls last longer.",
            priority=2,
        ),
        ResourceItem(
            name="Bar soap / liquid soap (equivalent)",
            quantity=float(soap_bars),
            unit="bars (equiv.)",
            notes="Handwashing is critical to prevent waterborne illness spread.",
            priority=1,
        ),
        ResourceItem(
            name="Hand sanitiser (≥60% alcohol)",
            quantity=float(hand_sanitiser_ml),
            unit="ml",
            notes=(
                f"~{int(_HAND_SANITISER_ML_PER_PERSON_DAY)} ml/person/day. "
                "Use when water/soap unavailable. Flammable — store away from heat."
            ),
            priority=1,
        ),
        ResourceItem(
            name="Heavy-duty garbage bags (60 L+)",
            quantity=float(garbage_bags),
            unit="bags",
            notes="Dual use: waste containment and improvised rain protection / waterproofing.",
            priority=2,
        ),
        ResourceItem(
            name="Household bleach (5% sodium hypochlorite)",
            quantity=float(bleach_l),
            unit="litres",
            notes=(
                "Surface disinfection and emergency water treatment. "
                "2 drops per litre for water purification. "
                "Do NOT mix with ammonia or acids."
            ),
            priority=2,
        ),
    ]

    # ---- Infant items ----
    if diapers > 0:
        items.append(
            ResourceItem(
                name="Disposable diapers / nappies",
                quantity=float(diapers),
                unit="units",
                notes=(
                    f"{_DIAPERS_PER_INFANT_DAY}/infant/day baseline. "
                    "Store flat in sealed bags to preserve absorbency."
                ),
                priority=1,
            )
        )

    if baby_wipes > 0:
        items.append(
            ResourceItem(
                name="Baby wipes (unscented, hypoallergenic)",
                quantity=float(baby_wipes),
                unit="wipes",
                notes=(
                    f"~{_BABY_WIPES_PER_PACK} wipes per {_BABY_WIPE_PACK_DAYS}-day period per infant. "
                    "Also useful as general personal wipes for adults when bathing water is scarce."
                ),
                priority=1,
            )
        )

    category_notes = (
        f"Sanitation plan for {total_humans} person(s) over {days} days "
        f"({vm.infants_count} infant(s))."
    )

    return CategoryResult(
        category="Sanitation",
        items=items,
        category_notes=category_notes,
    )
