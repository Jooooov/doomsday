"""
Response schemas for the checklist calculation endpoint.

These Pydantic models define the exact JSON structure returned by
POST /api/v1/checklist/calculate — one object per resource category.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Category-level response models
# ---------------------------------------------------------------------------

class WaterBreakdown(BaseModel):
    """Water and hydration category quantities."""
    drinking_water_litres: float = Field(
        ..., description="Litres of potable drinking water needed for the full duration"
    )
    sanitation_water_litres: float = Field(
        ..., description="Litres of non-potable water for hygiene/flushing"
    )
    total_water_litres: float = Field(
        ..., description="Total combined water supply required (litres)"
    )
    water_containers_5l: int = Field(
        ..., description="Number of 5-litre containers needed to store the total"
    )
    water_purification_tablets: int = Field(
        ..., description="Chlorine/iodine purification tablets as backup"
    )


class FoodBreakdown(BaseModel):
    """Food and nutrition category quantities."""
    total_calories_needed: int = Field(
        ..., description="Total kilocalories required for the planning period"
    )
    food_kg_total: float = Field(
        ..., description="Estimated total weight of shelf-stable food in kg"
    )
    rice_kg: float = Field(..., description="Rice / grains (kg)")
    canned_goods_kg: float = Field(..., description="Canned vegetables, meat, fish (kg)")
    dried_legumes_kg: float = Field(..., description="Lentils, beans, chickpeas (kg)")
    cooking_oil_litres: float = Field(..., description="Cooking oil (litres)")
    salt_g: float = Field(..., description="Iodised salt (grams)")
    sugar_g: float = Field(..., description="Sugar (grams)")
    infant_formula_tins: int = Field(
        default=0, description="900g tins of infant formula (0 if no infants)"
    )
    special_dietary_notes: List[str] = Field(
        default_factory=list,
        description="Human-readable notes for dietary restrictions, pregnancy, etc.",
    )


class MedicalBreakdown(BaseModel):
    """Medical and first-aid category quantities."""
    first_aid_kits: int
    bandages_rolls: int
    antiseptic_litres: float
    paracetamol_tablets: int
    ibuprofen_tablets: int
    oral_rehydration_sachets: int
    prescription_medication_buffer_days: int = Field(
        ..., description="Recommended days of prescription stock (duration + buffer)"
    )
    n95_masks: int
    latex_gloves_pairs: int
    thermometers: int
    blood_pressure_monitor: bool = Field(
        ..., description="Recommended for hypertensive or elderly members"
    )
    glucometer: bool = Field(
        ..., description="Recommended if any household member has diabetes"
    )
    extra_insulin_units: int = Field(
        default=0, description="Estimated insulin units buffer (0 if no diabetes)"
    )
    pregnancy_kit: bool = Field(
        default=False, description="Emergency pregnancy kit recommended"
    )
    notes: List[str] = Field(
        default_factory=list, description="Clinical guidance notes"
    )


class SanitationBreakdown(BaseModel):
    """Sanitation and hygiene category quantities."""
    toilet_paper_rolls: int
    soap_bars: int
    hand_sanitiser_ml: int
    garbage_bags_large: int
    feminine_hygiene_products: int = Field(
        ..., description="Estimated units (pads/tampons) for the period"
    )
    diapers: int = Field(default=0, description="Disposable diapers (0 if no infants)")
    baby_wipes: int = Field(default=0, description="Baby wipes packs (0 if no infants)")
    bleach_litres: float


class EnergyBreakdown(BaseModel):
    """Power and light category quantities."""
    candles: int
    matches_boxes: int
    flashlights: int
    batteries_aa: int
    batteries_aaa: int
    power_bank_units: int
    generator_recommended: bool
    fuel_litres_if_generator: float = Field(
        default=0.0,
        description="Litres of fuel if generator is recommended; 0 otherwise",
    )


class DocumentsBreakdown(BaseModel):
    """Documents and financial preparedness."""
    waterproof_document_pouch: int
    usb_drives_copies: int
    printed_emergency_contacts: bool
    cash_minimum_eur: float = Field(
        ..., description="Minimum physical cash recommended (EUR reference; adjust for local currency)"
    )


class PetsBreakdown(BaseModel):
    """Pet supplies (zero quantities when household has no pets)."""
    pet_food_kg: float
    pet_water_litres: float
    pet_medication_buffer_days: int
    pet_carrier_units: int
    notes: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class ChecklistCalculationResponse(BaseModel):
    """
    Complete response from POST /api/v1/checklist/calculate.

    All quantities are deterministic: the same profile + same formula version
    always produces identical numbers. No LLM involvement.
    """

    # ── Input echo for traceability ─────────────────────────────────────────
    profile_summary: "ProfileSummary" = Field(
        ..., description="Echo of key profile parameters used in the calculation"
    )

    # ── Per-category results ─────────────────────────────────────────────────
    water: WaterBreakdown
    food: FoodBreakdown
    medical: MedicalBreakdown
    sanitation: SanitationBreakdown
    energy: EnergyBreakdown
    documents: DocumentsBreakdown
    pets: PetsBreakdown

    # ── Metadata ─────────────────────────────────────────────────────────────
    formula_version: str = Field(
        "1.0.0", description="Formula library version — used for cache invalidation"
    )
    disclaimer: str = Field(
        default=(
            "These quantities are estimates based on standard emergency preparedness "
            "guidelines (FEMA, WHO, Red Cross, ANEPC). Adjust based on local conditions "
            "and specific health needs. This is NOT medical advice — consult a "
            "healthcare professional for health-related decisions."
        )
    )

    model_config = {"json_schema_extra": {"examples": []}}


class ProfileSummary(BaseModel):
    """Key profile parameters echoed back in the response for front-end display."""
    total_people: int
    adults: int
    children: int
    seniors: int
    total_pets: int
    preparation_days: int
    country: str
    climate_zone: str
    housing_type: str
    health_data_consent: bool


# Fix forward reference
ChecklistCalculationResponse.model_rebuild()
