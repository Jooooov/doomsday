"""
Profile schemas for Doomsday platform.

Defines the input/output structures for user profile data
and the normalized variable map consumed by guide generation formulas.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class PetType(str, Enum):
    DOG = "dog"
    CAT = "cat"
    BIRD = "bird"
    SMALL_ANIMAL = "small_animal"  # rabbits, hamsters, guinea pigs, etc.
    REPTILE = "reptile"
    FISH = "fish"
    OTHER = "other"


class MedicalCategory(str, Enum):
    """High-level medical need categories used in formula calculations."""
    MOBILITY_IMPAIRED = "mobility_impaired"      # wheelchair, walking aids
    REQUIRES_MEDICATION = "requires_medication"  # daily medication
    REQUIRES_POWER = "requires_power"            # CPAP, insulin pump, dialysis
    VISION_IMPAIRED = "vision_impaired"
    HEARING_IMPAIRED = "hearing_impaired"
    MENTAL_HEALTH = "mental_health"              # anxiety, PTSD, etc.
    CHRONIC_ILLNESS = "chronic_illness"          # diabetes, heart disease, etc.
    DIETARY_RESTRICTION = "dietary_restriction"  # celiac, severe allergy
    PREGNANCY = "pregnancy"
    INFANT_NEEDS = "infant_needs"                # formula, diapers


class DurationPreference(str, Enum):
    """Preferred survival/preparation duration."""
    DAYS_3 = "3_days"      # 72-hour kit
    WEEK_1 = "1_week"      # Standard emergency kit
    WEEKS_2 = "2_weeks"    # Extended preparedness
    MONTH_1 = "1_month"    # Serious preparedness
    MONTHS_3 = "3_months"  # Long-term preparedness
    MONTHS_6 = "6_months"  # Full prepper level


class RegionPreset(str, Enum):
    """Pre-generated content regions available in MVP."""
    PORTUGAL = "PT"
    USA = "US"
    OTHER = "OTHER"  # Falls back to generic guide


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class PetInfo(BaseModel):
    """Describes a pet type and quantity."""
    type: PetType = Field(..., description="Type of pet")
    count: Annotated[int, Field(ge=1, le=20)] = Field(
        ..., description="Number of pets of this type"
    )

    model_config = {"use_enum_values": True}


class MedicalNeed(BaseModel):
    """A declared medical need with optional free-text notes."""
    category: MedicalCategory = Field(
        ..., description="Standardised medical need category"
    )
    notes: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional user notes (not persisted unless GDPR consent given)",
    )

    model_config = {"use_enum_values": True}


class RegionInfo(BaseModel):
    """Geographic region for the user."""
    country_code: str = Field(
        ...,
        min_length=2,
        max_length=3,
        pattern=r"^[A-Z]{2,3}$",
        description="ISO 3166-1 alpha-2 or alpha-3 country code (uppercase)",
    )
    city: Optional[str] = Field(
        None, max_length=100, description="City or municipality name"
    )
    latitude: Optional[float] = Field(
        None, ge=-90.0, le=90.0, description="WGS-84 latitude"
    )
    longitude: Optional[float] = Field(
        None, ge=-180.0, le=180.0, description="WGS-84 longitude"
    )

    @field_validator("country_code", mode="before")
    @classmethod
    def normalise_country_code(cls, v: str) -> str:
        return v.strip().upper()


# ---------------------------------------------------------------------------
# Main input schema
# ---------------------------------------------------------------------------

class UserProfile(BaseModel):
    """
    Raw user profile as submitted by the frontend.
    All personal data is treated as session-scoped unless
    the user explicitly grants GDPR consent for persistence.
    """
    # ---- Household composition ----
    adults: Annotated[int, Field(ge=0, le=50)] = Field(
        1, description="Number of adults in the household (18–64)"
    )
    children: Annotated[int, Field(ge=0, le=20)] = Field(
        0, description="Number of children (under 18)"
    )
    seniors: Annotated[int, Field(ge=0, le=20)] = Field(
        0, description="Number of seniors (65+)"
    )
    pets: List[PetInfo] = Field(
        default_factory=list,
        max_length=10,
        description="Pets in the household, grouped by type",
    )

    # ---- Health & special needs ----
    medical_needs: List[MedicalNeed] = Field(
        default_factory=list,
        max_length=20,
        description="Declared medical/health needs",
    )
    health_data_consent: bool = Field(
        False,
        description="GDPR consent flag — health data not persisted without explicit opt-in",
    )

    # ---- Preparation preferences ----
    duration_preference: DurationPreference = Field(
        DurationPreference.WEEK_1,
        description="Target duration for the survival/prep guide",
    )

    # ---- Location ----
    region: RegionInfo = Field(
        ..., description="User's geographic region"
    )

    model_config = {
        "use_enum_values": True,
        "json_schema_extra": {
            "example": {
                "adults": 2,
                "children": 1,
                "seniors": 0,
                "pets": [{"type": "dog", "count": 1}],
                "medical_needs": [{"category": "requires_medication", "notes": None}],
                "health_data_consent": True,
                "duration_preference": "2_weeks",
                "region": {
                    "country_code": "PT",
                    "city": "Lisboa",
                    "latitude": 38.7169,
                    "longitude": -9.1399,
                },
            }
        },
    }

    @model_validator(mode="after")
    def require_at_least_one_person(self) -> "UserProfile":
        total = self.adults + self.children + self.seniors
        if total == 0:
            raise ValueError(
                "Household must have at least one person (adults + children + seniors >= 1)"
            )
        return self


# ---------------------------------------------------------------------------
# Normalised output variable map
# ---------------------------------------------------------------------------

class ProfileVariableMap(BaseModel):
    """
    Flat, formula-ready variable map produced by ProfileExtractor.

    All raw profile fields are normalised, derived fields are pre-calculated,
    and region context is enriched.  This is the single source of truth
    consumed by every guide-generation formula.
    """

    # ---- Household totals ----
    total_people: int = Field(..., description="Total household members")
    adults: int
    children: int
    seniors: int
    vulnerable_count: int = Field(
        ..., description="children + seniors (require extra resources)"
    )

    # ---- Pets ----
    has_pets: bool
    pet_count: int = Field(..., description="Total number of pets across all types")
    pet_types: List[str] = Field(..., description="Distinct pet type strings present")
    has_large_pets: bool = Field(
        ..., description="True if dogs or large animals present (affects evacuation)"
    )

    # ---- Medical ----
    has_medical_needs: bool
    medical_categories: List[str] = Field(
        ..., description="Distinct medical category strings (consent-filtered)"
    )
    requires_power_dependency: bool = Field(
        ...,
        description="True if any household member depends on powered medical device",
    )
    requires_medication: bool
    has_mobility_limitation: bool
    has_dietary_restriction: bool
    has_pregnancy: bool
    has_infant_needs: bool

    # ---- Duration ----
    duration_preference: str = Field(
        ..., description="Raw duration preference enum value"
    )
    duration_days: int = Field(
        ..., description="Duration in days derived from preference"
    )

    # ---- Resource multipliers (used directly in formulas) ----
    water_liters_per_day: float = Field(
        ...,
        description="Total household water need in litres/day (3L adult, 2L child/senior, 0.5L/pet)",
    )
    water_liters_total: float = Field(
        ..., description="Total water for the full duration"
    )
    food_units_per_day: float = Field(
        ...,
        description="Food units per day (1 unit=adult, 0.75=child/senior, 0 for pets handled separately)",
    )
    food_units_total: float = Field(
        ..., description="Total food units for the full duration"
    )
    medication_days_supply: int = Field(
        ...,
        description="Days of medication supply recommended (duration_days + 30% buffer)",
    )

    # ---- Region ----
    region_country_code: str
    region_preset: str = Field(
        ..., description="Matched preset ('PT', 'US', 'OTHER')"
    )
    region_city: Optional[str]
    region_latitude: Optional[float]
    region_longitude: Optional[float]
    region_has_coordinates: bool

    # ---- Guide personalisation flags ----
    guide_language_hint: str = Field(
        ...,
        description="Suggested guide language based on country (ISO 639-1)",
    )
    needs_evacuation_planning: bool = Field(
        ...,
        description="True if profile suggests extra evacuation complexity (pets, mobility, infants)",
    )
    complexity_score: int = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "0-100 score of household preparation complexity "
            "(drives LLM prompt verbosity)"
        ),
    )

    # ---- Metadata ----
    health_data_consent: bool = Field(
        ...,
        description="Whether medical details can be included in persisted records",
    )
    extraction_version: str = Field(
        "1.0.0",
        description="Version of the extraction logic (for cache busting)",
    )
