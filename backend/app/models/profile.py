"""
Profile models for user survival preparation data.
Used as input to the formula engine for checklist quantity calculations.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class AgeGroup(str, Enum):
    INFANT = "infant"        # 0-2 years
    CHILD = "child"          # 3-12 years
    TEEN = "teen"            # 13-17 years
    ADULT = "adult"          # 18-64 years
    SENIOR = "senior"        # 65+


class ActivityLevel(str, Enum):
    SEDENTARY = "sedentary"
    MODERATE = "moderate"
    ACTIVE = "active"


class ClimateZone(str, Enum):
    TEMPERATE = "temperate"
    HOT_DRY = "hot_dry"
    HOT_HUMID = "hot_humid"
    COLD = "cold"
    ARCTIC = "arctic"


class HousingType(str, Enum):
    APARTMENT = "apartment"
    HOUSE = "house"
    RURAL = "rural"
    MOBILE = "mobile"


class HealthCondition(str, Enum):
    DIABETES = "diabetes"
    HYPERTENSION = "hypertension"
    HEART_DISEASE = "heart_disease"
    RESPIRATORY = "respiratory"       # asthma, COPD
    KIDNEY_DISEASE = "kidney_disease"
    IMMUNOCOMPROMISED = "immunocompromised"
    MOBILITY_IMPAIRED = "mobility_impaired"
    MENTAL_HEALTH = "mental_health"
    PREGNANCY = "pregnancy"
    INFANT_CARE = "infant_care"       # breastfeeding / formula-feeding


class DietaryRestriction(str, Enum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    GLUTEN_FREE = "gluten_free"
    HALAL = "halal"
    KOSHER = "kosher"
    NUT_ALLERGY = "nut_allergy"
    DAIRY_FREE = "dairy_free"


class PetType(str, Enum):
    DOG_SMALL = "dog_small"      # < 10 kg
    DOG_MEDIUM = "dog_medium"    # 10-25 kg
    DOG_LARGE = "dog_large"      # > 25 kg
    CAT = "cat"
    BIRD = "bird"
    OTHER = "other"


class Pet(BaseModel):
    type: PetType
    count: int = Field(default=1, ge=1, le=10)


class FamilyMember(BaseModel):
    age_group: AgeGroup
    count: int = Field(default=1, ge=1, le=20)
    activity_level: ActivityLevel = ActivityLevel.MODERATE
    health_conditions: List[HealthCondition] = Field(default_factory=list)
    dietary_restrictions: List[DietaryRestriction] = Field(default_factory=list)

    @field_validator("count")
    @classmethod
    def count_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Count must be at least 1")
        return v


class UserProfile(BaseModel):
    """
    Full user profile for survival guide personalization.
    Either profile_id (for DB lookup) or inline data must be provided.
    """
    # Identifiers
    profile_id: Optional[str] = Field(
        default=None,
        description="Existing profile UUID for DB lookup"
    )

    # Household composition
    family_members: List[FamilyMember] = Field(
        default_factory=list,
        description="List of family member groups by age category"
    )
    pets: List[Pet] = Field(default_factory=list)

    # Location & environment
    country: str = Field(default="PT", description="ISO 3166-1 alpha-2 country code")
    region: Optional[str] = Field(default=None, description="Region/state/province")
    climate_zone: ClimateZone = ClimateZone.TEMPERATE
    housing_type: HousingType = HousingType.APARTMENT

    # Preparation parameters
    preparation_days: int = Field(
        default=30,
        ge=3,
        le=365,
        description="Number of days to prepare supplies for"
    )
    storage_space_m3: Optional[float] = Field(
        default=None,
        ge=0,
        description="Available storage space in cubic meters (optional constraint)"
    )

    # Health data — requires explicit GDPR consent
    health_data_consent: bool = Field(
        default=False,
        description="GDPR explicit consent for processing health data"
    )

    @model_validator(mode="after")
    def validate_health_data(self) -> "UserProfile":
        """
        GDPR compliance: health conditions require explicit consent.
        Strip health data if consent is not given.
        """
        if not self.health_data_consent:
            for member in self.family_members:
                member.health_conditions = []
        return self

    @property
    def total_adults(self) -> int:
        return sum(
            m.count for m in self.family_members
            if m.age_group in (AgeGroup.ADULT, AgeGroup.SENIOR, AgeGroup.TEEN)
        )

    @property
    def total_children(self) -> int:
        return sum(
            m.count for m in self.family_members
            if m.age_group in (AgeGroup.CHILD, AgeGroup.INFANT)
        )

    @property
    def total_people(self) -> int:
        return sum(m.count for m in self.family_members)

    @property
    def total_pets(self) -> int:
        return sum(p.count for p in self.pets)
