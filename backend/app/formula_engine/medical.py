"""
Medical & First-Aid supply formula — deterministic, pure functions only.

Baselines from:
  - FEMA emergency preparedness guidelines
  - Red Cross first aid kit standards
  - WHO essential medicines lists

No LLM.  No randomness.  Same inputs → same outputs, always.
"""

from __future__ import annotations

import math
from typing import Optional

from .models import (
    CategoryResult,
    ResourceItem,
    VariableMap,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MEDICATION_BUFFER_DAYS = 7           # extra days of prescription supply

# OTC dosing assumptions (tablets per person per day, worst-case):
# paracetamol: up to 4 doses × 2-day incidence per week  →  8/person/week
# ibuprofen:   up to 3 doses × 2-day incidence per week  →  6/person/week
# ORS:         3 sachets/person/week (diarrhoea prophylaxis)
_PARACETAMOL_PER_PERSON_WEEK = 8
_IBUPROFEN_PER_PERSON_WEEK   = 6
_ORS_PER_PERSON_WEEK         = 3

# N95 masks: 1 per person per 3 days (WHO recommended use period)
_MASK_DAYS_PER_UNIT = 3

# Gloves: 5 pairs per person per week
_GLOVES_PAIRS_PER_PERSON_WEEK = 5

# Antiseptic: 0.1 L per standard-person per week
_ANTISEPTIC_L_PER_STD_PERSON_WEEK = 0.1


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _weeks(days: int) -> int:
    """Ceiling-round duration to whole weeks."""
    return math.ceil(days / 7)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_medical(vm: VariableMap) -> CategoryResult:
    """
    Returns the medical category result for the given variable map.

    Pure function: deterministic, no side-effects, no I/O.
    """
    days          = vm.duration_days
    total_humans  = vm.total_humans
    std_persons   = vm.total_standard_persons
    wks           = _weeks(days)

    # ---- First-aid kits ----
    # 1 kit per household; +1 per additional 4 people
    first_aid_kits = max(1, math.ceil(total_humans / 4))

    # ---- Bandages ----
    bandages = total_humans * 2
    if vm.children_count > 0:
        # Children are more prone to minor injuries (+50%)
        bandages = math.ceil(bandages * 1.5)

    # ---- Antiseptic ----
    antiseptic_l = max(0.5, round(std_persons * _ANTISEPTIC_L_PER_STD_PERSON_WEEK * wks, 2))

    # ---- OTC medications ----
    paracetamol_tablets = total_humans * _PARACETAMOL_PER_PERSON_WEEK * wks
    ibuprofen_tablets   = total_humans * _IBUPROFEN_PER_PERSON_WEEK   * wks
    ors_sachets         = total_humans * _ORS_PER_PERSON_WEEK         * wks

    # ---- PPE ----
    n95_masks         = total_humans * math.ceil(days / _MASK_DAYS_PER_UNIT)
    gloves_pairs      = total_humans * _GLOVES_PAIRS_PER_PERSON_WEEK * wks
    tourniquet_units  = max(1, math.ceil(total_humans / 4))
    thermometer_units = max(1, math.ceil(total_humans / 4))

    # ---- Prescription medication buffer ----
    # Only included when there are registered medications (GDPR-consent gated in VariableMap)
    medication_buffer_days: Optional[int] = None
    if vm.medications:
        medication_buffer_days = days + _MEDICATION_BUFFER_DAYS

    # ---- Diabetic supplies ----
    insulin_vials = 0
    glucometer_strips = 0
    if vm.has_diabetic and vm.health_data_consent:
        # Conservative estimate: ~0.3 vials (10mL, U-100) per diabetic person per day
        # Each vial = 1000 units; avg dose ~30 units/day  →  30 units/day / 1000 = 0.03 vials/day
        # Round to vials of 10mL
        vials_per_day = 0.03
        insulin_vials = math.ceil(total_humans * vials_per_day * (days + _MEDICATION_BUFFER_DAYS))
        glucometer_strips = total_humans * 4 * (days + _MEDICATION_BUFFER_DAYS)  # 4 tests/day

    # ---- Build items ----
    items = [
        ResourceItem(
            name="First-aid kit (complete)",
            quantity=float(first_aid_kits),
            unit="kits",
            notes=(
                "Include bandages, gauze, scissors, tweezers, antiseptic wipes, "
                "adhesive tape, CPR mask, disposable gloves."
            ),
            priority=1,
        ),
        ResourceItem(
            name="Bandage / gauze rolls (sterile)",
            quantity=float(bandages),
            unit="rolls",
            notes="5 cm × 5 m rolls; suitable for moderate wound dressing.",
            priority=1,
        ),
        ResourceItem(
            name="Antiseptic solution (e.g. chlorhexidine 2%)",
            quantity=float(antiseptic_l),
            unit="litres",
            notes="Wound irrigation and surface disinfection.",
            priority=1,
        ),
        ResourceItem(
            name="Paracetamol 500 mg tablets",
            quantity=float(paracetamol_tablets),
            unit="tablets",
            notes="Max 8 tablets/adult/day; lower dose for children — see packaging.",
            priority=1,
        ),
        ResourceItem(
            name="Ibuprofen 400 mg tablets",
            quantity=float(ibuprofen_tablets),
            unit="tablets",
            notes="Anti-inflammatory / analgesic. Avoid on empty stomach.",
            priority=2,
        ),
        ResourceItem(
            name="Oral Rehydration Salts (ORS sachets)",
            quantity=float(ors_sachets),
            unit="sachets",
            notes="Critical for diarrhoea management; dissolve 1 sachet in 1 L of clean water.",
            priority=1,
        ),
        ResourceItem(
            name="N95 / FFP2 respirator masks",
            quantity=float(n95_masks),
            unit="masks",
            notes="1 mask per person per 3 days; store in sealed bag until use.",
            priority=2,
        ),
        ResourceItem(
            name="Nitrile gloves (examination grade)",
            quantity=float(gloves_pairs),
            unit="pairs",
            notes="Powder-free, size M–L. Use when handling wounds or body fluids.",
            priority=1,
        ),
        ResourceItem(
            name="Tourniquet (CAT or SOFT-T Wide)",
            quantity=float(tourniquet_units),
            unit="units",
            notes=(
                "Life-saving haemorrhage control. "
                "All adults should know how to apply. "
                "Check condition every 6 months."
            ),
            priority=1,
        ),
        ResourceItem(
            name="Digital thermometer",
            quantity=float(thermometer_units),
            unit="units",
            notes="Non-contact (IR) preferred; keep one per sleeping area in large groups.",
            priority=2,
        ),
    ]

    # Prescription medication buffer item
    if medication_buffer_days is not None:
        med_names = ", ".join(m.name for m in vm.medications[:3])
        if len(vm.medications) > 3:
            med_names += f" (+{len(vm.medications) - 3} more)"
        items.append(
            ResourceItem(
                name="Prescription medications (emergency stock)",
                quantity=float(medication_buffer_days),
                unit="days supply",
                notes=(
                    f"Stock for: {med_names}. "
                    f"Ensure {_MEDICATION_BUFFER_DAYS}-day buffer beyond planning horizon. "
                    "Store in cool, dark location; check temperature requirements."
                ),
                priority=1,
            )
        )

    # Insulin + glucometer strips
    if insulin_vials > 0:
        items.append(
            ResourceItem(
                name="Insulin (rapid-acting, U-100 vials)",
                quantity=float(insulin_vials),
                unit="vials (10 mL)",
                notes=(
                    "Requires refrigeration (2–8 °C); once opened stable 28 days at room temp. "
                    "Consult endocrinologist for precise personal dosage."
                ),
                priority=1,
            )
        )
        items.append(
            ResourceItem(
                name="Glucometer test strips",
                quantity=float(glucometer_strips),
                unit="strips",
                notes="4 tests/person/day minimum; store below 30 °C away from humidity.",
                priority=1,
            )
        )

    category_notes = (
        f"Medical plan for {total_humans} person(s) over {days} days. "
        "This is a preparedness estimate — not medical advice. "
        "Always consult a medical professional for personal health decisions."
    )

    return CategoryResult(
        category="Medical",
        items=items,
        category_notes=category_notes,
    )
