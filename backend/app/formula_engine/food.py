"""
Food formula — deterministic, pure functions only.

Caloric baseline from USDA/WHO:
  Adult male    2000 kcal/day sedentary → 3000 kcal/day high-exertion
  Adult female  1800 kcal/day sedentary → 2400 kcal/day high-exertion
  Child (avg)   1400 kcal/day (6-12 yo reference)
  Elderly       1600 kcal/day sedentary
  Infant        700 kcal/day (formula / puree)

We use a simplified per-person model weighted by person type.

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
# Caloric constants
# ---------------------------------------------------------------------------

# Sedentary baseline kcal/day by person type
_KCAL_ADULT_SEDENTARY   = 2000.0
_KCAL_CHILD_SEDENTARY   = 1400.0
_KCAL_ELDERLY_SEDENTARY = 1600.0
_KCAL_INFANT_DAY        = 700.0   # formula + solids, fixed regardless of exertion

# High-exertion delta (added when exertion_factor = 1.0)
_KCAL_ADULT_EXERTION_DELTA   = 1000.0
_KCAL_CHILD_EXERTION_DELTA   = 600.0
_KCAL_ELDERLY_EXERTION_DELTA = 400.0

# Cold climate adds ~10% extra calories (thermoregulation)
_CLIMATE_KCAL_MULTIPLIER: dict[ClimateZone, float] = {
    ClimateZone.HOT:       0.95,
    ClimateZone.TROPICAL:  0.95,
    ClimateZone.TEMPERATE: 1.00,
    ClimateZone.COLD:      1.10,
}

# Threat-level storage buffer (same logic as water)
def _threat_buffer(threat_level: int) -> float:
    return 1.0 + (threat_level - 1) * (0.40 - 0.10) / 9.0


# ---------------------------------------------------------------------------
# Stockpile assumptions (energy density)
# ---------------------------------------------------------------------------

# kcal per kg for common shelf-stable foods
_KCAL_PER_KG: dict[str, float] = {
    "rice":              3600.0,
    "pasta":             3500.0,
    "rolled_oats":       3800.0,
    "canned_beans":      900.0,   # drained
    "canned_tuna":       1000.0,
    "canned_tomatoes":   200.0,
    "cooking_oil":       8840.0,
    "crackers":          4000.0,
    "dried_lentils":     3530.0,
    "peanut_butter":     5880.0,
    "honey":             3040.0,
    "multivitamins":     0.0,     # no calories but listed separately
}

# Target macro allocation (% of calories)
_CARB_PCT  = 0.50
_PROTEIN_PCT = 0.25
_FAT_PCT   = 0.25


def _daily_kcal_per_person_type(vm: VariableMap) -> dict[str, float]:
    """Return kcal/day for each person type given the exertion factor."""
    ef  = vm.expected_exertion_factor
    clm = _CLIMATE_KCAL_MULTIPLIER[vm.climate_zone]

    return {
        "adult":   (_KCAL_ADULT_SEDENTARY   + ef * _KCAL_ADULT_EXERTION_DELTA)   * clm,
        "child":   (_KCAL_CHILD_SEDENTARY   + ef * _KCAL_CHILD_EXERTION_DELTA)   * clm,
        "elderly": (_KCAL_ELDERLY_SEDENTARY + ef * _KCAL_ELDERLY_EXERTION_DELTA) * clm,
        "infant":  _KCAL_INFANT_DAY,  # fixed
    }


def calculate_food(vm: VariableMap) -> CategoryResult:
    """
    Returns the food category result for the given variable map.

    Pure function: deterministic, no side-effects, no I/O.
    """
    days   = vm.duration_days
    buf    = _threat_buffer(vm.threat_level)
    kcal_d = _daily_kcal_per_person_type(vm)

    # ---- Total kcal needed ----
    total_kcal = (
        vm.adults_count   * kcal_d["adult"]
        + vm.children_count * kcal_d["child"]
        + vm.elderly_count  * kcal_d["elderly"]
        + vm.infants_count  * kcal_d["infant"]
    ) * days * buf

    # ---- Breakdown by macro source ----
    carb_kcal    = total_kcal * _CARB_PCT
    protein_kcal = total_kcal * _PROTEIN_PCT
    fat_kcal     = total_kcal * _FAT_PCT

    # ---- Allocate to food items ----
    # Carbs: 60% rice, 40% pasta/oats
    rice_kg      = math.ceil((carb_kcal * 0.60) / _KCAL_PER_KG["rice"]       * 10) / 10
    pasta_kg     = math.ceil((carb_kcal * 0.25) / _KCAL_PER_KG["pasta"]      * 10) / 10
    oats_kg      = math.ceil((carb_kcal * 0.15) / _KCAL_PER_KG["rolled_oats"]* 10) / 10

    # Protein: 40% beans, 30% lentils, 30% canned fish
    beans_kg     = math.ceil((protein_kcal * 0.40) / _KCAL_PER_KG["canned_beans"] * 10) / 10
    lentils_kg   = math.ceil((protein_kcal * 0.30) / _KCAL_PER_KG["dried_lentils"]* 10) / 10
    tuna_kg      = math.ceil((protein_kcal * 0.30) / _KCAL_PER_KG["canned_tuna"]  * 10) / 10

    # Fat: 60% oil, 40% peanut butter
    oil_litres   = math.ceil((fat_kcal * 0.60) / _KCAL_PER_KG["cooking_oil"] * 10) / 10  # oil ~0.92 kg/L
    pb_kg        = math.ceil((fat_kcal * 0.40) / _KCAL_PER_KG["peanut_butter"]* 10) / 10

    # Supplementary items (fixed per person)
    crackers_kg  = math.ceil(vm.total_standard_persons * days * 0.05 * 10) / 10  # ~50g/day
    honey_kg     = math.ceil(vm.total_standard_persons * days * 0.02 * 10) / 10  # ~20g/day
    canned_tom_kg= math.ceil(vm.total_standard_persons * days * 0.10 * 10) / 10  # flavour/veg

    # Infant formula (only if infants present)
    infant_formula_kg = 0.0
    if vm.infants_count > 0:
        # ~180g dry formula per infant per day
        infant_formula_kg = math.ceil(vm.infants_count * days * 0.18 * 10) / 10

    # Pet food
    pet_food_kg = 0.0
    from .models import PetSpecies
    for pet in vm.pets:
        if pet.species == PetSpecies.DOG:
            pet_food_kg += pet.weight_kg * 0.025 * pet.count * days   # ~2.5% BW/day
        elif pet.species == PetSpecies.CAT:
            pet_food_kg += 0.060 * pet.count * days                   # ~60g/day fixed
        elif pet.species == PetSpecies.BIRD:
            pet_food_kg += 0.030 * pet.count * days                   # ~30g seeds/day
        else:
            pet_food_kg += pet.weight_kg * 0.025 * pet.count * days
    pet_food_kg = math.ceil(pet_food_kg * 10) / 10

    # Multivitamins
    multivit_units = vm.total_humans * days

    # ---- Avg kcal/day sanity figure ----
    avg_kcal_per_person_day = round(
        total_kcal / (vm.total_humans * days) if vm.total_humans > 0 else 0, 0
    )

    items = [
        # Carbs
        ResourceItem(
            name="White rice (long-grain, dried)",
            quantity=rice_kg,
            unit="kg",
            notes="5+ year shelf-life in sealed mylar bags with oxygen absorbers.",
            priority=1,
        ),
        ResourceItem(
            name="Pasta (dried)",
            quantity=pasta_kg,
            unit="kg",
            notes="Store in airtight containers away from light.",
            priority=1,
        ),
        ResourceItem(
            name="Rolled oats",
            quantity=oats_kg,
            unit="kg",
            notes="Good for quick cold-water cooking (reduces fuel use).",
            priority=2,
        ),
        # Protein
        ResourceItem(
            name="Canned beans (mixed, drained weight)",
            quantity=beans_kg,
            unit="kg",
            notes="Check for BPA-free cans; rotate every 3-5 years.",
            priority=1,
        ),
        ResourceItem(
            name="Dried lentils",
            quantity=lentils_kg,
            unit="kg",
            notes="Cook in 20 min without soaking — fuel efficient.",
            priority=1,
        ),
        ResourceItem(
            name="Canned tuna / sardines",
            quantity=tuna_kg,
            unit="kg",
            notes="Complete protein; omega-3 beneficial in high-stress periods.",
            priority=1,
        ),
        # Fat
        ResourceItem(
            name="Cooking oil (sunflower or olive)",
            quantity=oil_litres,
            unit="litres",
            notes="Highest calorie density per volume; 2-year shelf life unopened.",
            priority=1,
        ),
        ResourceItem(
            name="Peanut butter",
            quantity=pb_kg,
            unit="kg",
            notes="High-calorie, no cooking required. Check for nut allergy.",
            priority=2,
        ),
        # Supplementary
        ResourceItem(
            name="Crackers / crispbread",
            quantity=crackers_kg,
            unit="kg",
            notes="Ready-to-eat morale booster; 1-2 year shelf life.",
            priority=2,
        ),
        ResourceItem(
            name="Honey",
            quantity=honey_kg,
            unit="kg",
            notes="Indefinite shelf life; natural antimicrobial.",
            priority=3,
        ),
        ResourceItem(
            name="Canned tomatoes / passata",
            quantity=canned_tom_kg,
            unit="kg",
            notes="Vitamins C & A; improves palatability of staples.",
            priority=2,
        ),
        # Micronutrients
        ResourceItem(
            name="Multivitamin tablets (complete formula)",
            quantity=float(multivit_units),
            unit="tablets",
            notes="One per person per day to offset nutritional gaps in stored diet.",
            priority=1,
        ),
        ResourceItem(
            name="Salt (iodised)",
            quantity=float(math.ceil(vm.total_standard_persons * days * 0.005 * 10) / 10),
            unit="kg",
            notes="~5 g/person/day for cooking; iodised for thyroid health.",
            priority=2,
        ),
    ]

    # Infant formula
    if infant_formula_kg > 0:
        items.append(
            ResourceItem(
                name="Infant formula (powder)",
                quantity=infant_formula_kg,
                unit="kg",
                notes=f"For {vm.infants_count} infant(s); verify expiry dates monthly.",
                priority=1,
            )
        )

    # Pet food
    if pet_food_kg > 0:
        items.append(
            ResourceItem(
                name="Pet food (dry, species-appropriate)",
                quantity=pet_food_kg,
                unit="kg",
                notes="Store in airtight container; rotate every 12 months.",
                priority=2,
            )
        )

    # Diabetic note item
    if vm.has_diabetic and vm.health_data_consent:
        items.append(
            ResourceItem(
                name="Low-GI food swaps (lentils, oats, barley)",
                quantity=float(math.ceil(vm.total_standard_persons * days * 0.05 * 10) / 10),
                unit="kg",
                notes="Substitute for rice where possible for diabetic household members.",
                priority=1,
            )
        )

    category_notes = (
        f"Food plan: {vm.total_humans} person(s), {days} days, "
        f"{avg_kcal_per_person_day:.0f} kcal/person/day average "
        f"(exertion {vm.expected_exertion_factor:.1f}, {vm.climate_zone.value} climate). "
        f"Total stored energy: {total_kcal:,.0f} kcal."
    )

    return CategoryResult(
        category="Food",
        items=items,
        category_notes=category_notes,
    )
