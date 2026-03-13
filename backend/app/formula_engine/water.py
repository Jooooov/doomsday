"""
Water formula — deterministic, pure functions only.

Baseline: FEMA/WHO recommend 3.78 L (1 US gallon) per person/day for drinking.
Total including sanitation is 3–6 L/day depending on climate.

No LLM.  No randomness.  Same inputs → same outputs, always.
"""

from __future__ import annotations

import math

from .models import (
    CategoryResult,
    ClimateZone,
    MobilityLevel,
    ResourceItem,
    VariableMap,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DRINKING_LITRES_PER_PERSON_DAY = 2.0      # WHO minimum drinking water
_SANITATION_LITRES_PER_PERSON_DAY = 2.0    # basic hygiene, not showering
_COOKING_LITRES_PER_PERSON_DAY = 1.0       # cooking & food prep

# Climate multipliers applied to sanitation only (drinking is fixed)
_CLIMATE_SANITATION_MULTIPLIER: dict[ClimateZone, float] = {
    ClimateZone.HOT:       1.5,
    ClimateZone.TROPICAL:  1.3,
    ClimateZone.TEMPERATE: 1.0,
    ClimateZone.COLD:      0.8,
}

# Infant water (formula mixing, etc.)
_INFANT_LITRES_PER_DAY = 1.0

# Pets — rough per-kg needs
_DOG_LITRES_PER_KG_DAY  = 0.06
_CAT_LITRES_PER_KG_DAY  = 0.04
_BIRD_LITRES_PER_UNIT_DAY = 0.05

# Threat multiplier: store extra when conflict is near
def _threat_buffer(threat_level: int) -> float:
    """Return a multiplier >1.0 to add a safety buffer based on threat."""
    # 1→ +10%, 10 → +40%
    return 1.0 + (threat_level - 1) * (0.40 - 0.10) / 9.0


def calculate_water(vm: VariableMap) -> CategoryResult:
    """
    Returns the water category result for the given variable map.

    Pure function: deterministic, no side-effects, no I/O.
    """
    days   = vm.duration_days
    clim_m = _CLIMATE_SANITATION_MULTIPLIER[vm.climate_zone]
    buf    = _threat_buffer(vm.threat_level)

    # ---- Drinking water ----
    std_persons = vm.total_standard_persons
    drinking_l  = _DRINKING_LITRES_PER_PERSON_DAY * std_persons * days * buf
    # Infants use a separate lower figure (included in std_persons at 0.1 weight
    # but we add a dedicated infant top-up)
    infant_topup_l = vm.infants_count * _INFANT_LITRES_PER_DAY * days

    # ---- Sanitation water ----
    sanitation_l = _SANITATION_LITRES_PER_PERSON_DAY * clim_m * std_persons * days * buf

    # ---- Cooking water ----
    cooking_l = _COOKING_LITRES_PER_PERSON_DAY * std_persons * days

    # ---- Pet water ----
    pet_l = 0.0
    from .models import PetSpecies
    for pet in vm.pets:
        if pet.species == PetSpecies.DOG:
            pet_l += _DOG_LITRES_PER_KG_DAY * pet.weight_kg * pet.count * days
        elif pet.species == PetSpecies.CAT:
            pet_l += _CAT_LITRES_PER_KG_DAY * pet.weight_kg * pet.count * days
        elif pet.species == PetSpecies.BIRD:
            pet_l += _BIRD_LITRES_PER_UNIT_DAY * pet.count * days
        else:
            # Generic: treat like small dog
            pet_l += _DOG_LITRES_PER_KG_DAY * pet.weight_kg * pet.count * days

    # ---- Totals (rounded up to nearest litre) ----
    human_total_l = math.ceil(drinking_l + infant_topup_l + sanitation_l + cooking_l)
    pet_total_l   = math.ceil(pet_l)
    grand_total_l = human_total_l + pet_total_l

    # If they have well water: reduce stored need by 50% (but keep 3-day reserve minimum)
    stored_l = grand_total_l
    if vm.has_well_water:
        minimum_reserve_l = math.ceil(
            (_DRINKING_LITRES_PER_PERSON_DAY + _SANITATION_LITRES_PER_PERSON_DAY)
            * vm.total_standard_persons * 3
        )
        stored_l = max(minimum_reserve_l, math.ceil(grand_total_l * 0.5))

    # Container recommendation: 20-litre jerry-cans
    jerry_cans = math.ceil(stored_l / 20.0)

    # ---- Notes ----
    notes_parts = [
        f"Drinking: {math.ceil(drinking_l + infant_topup_l)} L, "
        f"Sanitation: {math.ceil(sanitation_l)} L, "
        f"Cooking: {math.ceil(cooking_l)} L."
    ]
    if vm.has_well_water:
        notes_parts.append("Well water detected — only a 50% stockpile is required (minimum 3-day reserve).")
    if pet_total_l > 0:
        notes_parts.append(f"Pets require an additional {pet_total_l} L.")
    notes_parts.append("Use food-grade HDPE containers; rotate every 6 months.")

    items = [
        ResourceItem(
            name="Drinking / Sanitation / Cooking Water",
            quantity=float(stored_l),
            unit="litres",
            notes=" ".join(notes_parts),
            priority=1,
        ),
        ResourceItem(
            name="20 L food-grade jerry-cans (or equivalent containers)",
            quantity=float(jerry_cans),
            unit="units",
            notes="Fill with tap water; add 2 drops unscented 5% bleach per litre if storing >1 month.",
            priority=1,
        ),
        ResourceItem(
            name="Water purification tablets (chlorine-based)",
            quantity=float(days * vm.total_humans * 2),  # 2 tablets/person/day as buffer
            unit="tablets",
            notes="Backup purification in case stored supply runs out or becomes contaminated.",
            priority=2,
        ),
        ResourceItem(
            name="Portable water filter (e.g. LifeStraw or Sawyer Squeeze)",
            quantity=1.0,
            unit="unit",
            notes="Tertiary backup; filters up to 1,000 L each.",
            priority=2,
        ),
    ]

    # Collapsible water container for mobile evacuation
    if vm.mobility_level == MobilityLevel.MOBILE:
        items.append(
            ResourceItem(
                name="Collapsible water bag (10 L, for evacuation)",
                quantity=float(max(1, vm.adults_count)),
                unit="units",
                notes="One per adult for on-foot evacuation.",
                priority=2,
            )
        )

    category_notes = (
        f"Water plan for {vm.total_humans} person(s) over {days} days "
        f"({vm.climate_zone.value} climate, threat level {vm.threat_level}/10). "
        f"Total stored: {stored_l} L."
    )

    return CategoryResult(
        category="Water",
        items=items,
        category_notes=category_notes,
    )
