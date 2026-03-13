"""
Profile Adapter — converts the API-facing UserProfile (schemas/profile.py)
into the formula engine's internal UserProfile (models/profile.py).

This decoupling keeps the public API stable regardless of internal model changes.
"""
from __future__ import annotations

from typing import Dict

from app.models.profile import (
    ActivityLevel,
    AgeGroup,
    ClimateZone,
    DietaryRestriction,
    FamilyMember,
    HealthCondition,
    HousingType,
    Pet,
    PetType as ModelPetType,
    UserProfile as FormulaUserProfile,
)
from app.schemas.profile import (
    DurationPreference,
    MedicalCategory,
    PetInfo,
    PetType as SchemaPetType,
    UserProfile as ApiUserProfile,
)


# ---------------------------------------------------------------------------
# Duration mapping
# ---------------------------------------------------------------------------

DURATION_DAYS: Dict[str, int] = {
    DurationPreference.DAYS_3.value:   3,
    DurationPreference.WEEK_1.value:   7,
    DurationPreference.WEEKS_2.value:  14,
    DurationPreference.MONTH_1.value:  30,
    DurationPreference.MONTHS_3.value: 90,
    DurationPreference.MONTHS_6.value: 180,
}


# ---------------------------------------------------------------------------
# Pet type mapping
# ---------------------------------------------------------------------------

_PET_TYPE_MAP: Dict[str, ModelPetType] = {
    SchemaPetType.DOG.value:          ModelPetType.DOG_MEDIUM,  # default to medium
    SchemaPetType.CAT.value:          ModelPetType.CAT,
    SchemaPetType.BIRD.value:         ModelPetType.BIRD,
    SchemaPetType.SMALL_ANIMAL.value: ModelPetType.OTHER,
    SchemaPetType.REPTILE.value:      ModelPetType.OTHER,
    SchemaPetType.FISH.value:         ModelPetType.OTHER,
    SchemaPetType.OTHER.value:        ModelPetType.OTHER,
}


def _map_pet_type(schema_type: str) -> ModelPetType:
    return _PET_TYPE_MAP.get(schema_type, ModelPetType.OTHER)


# ---------------------------------------------------------------------------
# Medical category → HealthCondition mapping
# ---------------------------------------------------------------------------

_MEDICAL_TO_HEALTH: Dict[str, list[HealthCondition]] = {
    MedicalCategory.MOBILITY_IMPAIRED.value:   [HealthCondition.MOBILITY_IMPAIRED],
    MedicalCategory.REQUIRES_MEDICATION.value: [],  # handled via prescription_medication_buffer
    MedicalCategory.REQUIRES_POWER.value:      [],  # flagged separately; no direct HealthCondition
    MedicalCategory.VISION_IMPAIRED.value:     [],
    MedicalCategory.HEARING_IMPAIRED.value:    [],
    MedicalCategory.MENTAL_HEALTH.value:       [HealthCondition.MENTAL_HEALTH],
    MedicalCategory.CHRONIC_ILLNESS.value:     [HealthCondition.DIABETES],  # proxy for chronic
    MedicalCategory.DIETARY_RESTRICTION.value: [],
    MedicalCategory.PREGNANCY.value:           [HealthCondition.PREGNANCY],
    MedicalCategory.INFANT_NEEDS.value:        [HealthCondition.INFANT_CARE],
}


def _medical_categories_to_health_conditions(
    categories: list[str],
    health_data_consent: bool,
) -> list[HealthCondition]:
    """
    Convert API medical categories to formula-engine HealthCondition enums.
    If consent is not given the formula engine itself will strip these anyway,
    but we still pass them so the engine's GDPR validator can act as the
    single source of truth.
    """
    if not health_data_consent:
        return []

    conditions: list[HealthCondition] = []
    for cat in categories:
        mapped = _MEDICAL_TO_HEALTH.get(cat, [])
        for hc in mapped:
            if hc not in conditions:
                conditions.append(hc)
    return conditions


# ---------------------------------------------------------------------------
# Country code → ClimateZone heuristic
# ---------------------------------------------------------------------------

_COUNTRY_CLIMATE: Dict[str, ClimateZone] = {
    "PT": ClimateZone.TEMPERATE,  # Portugal — Mediterranean
    "ES": ClimateZone.TEMPERATE,
    "FR": ClimateZone.TEMPERATE,
    "DE": ClimateZone.TEMPERATE,
    "UK": ClimateZone.TEMPERATE,
    "GB": ClimateZone.TEMPERATE,
    "IT": ClimateZone.TEMPERATE,
    "US": ClimateZone.TEMPERATE,  # simplified; US spans many zones
    "CA": ClimateZone.COLD,
    "RU": ClimateZone.COLD,
    "NO": ClimateZone.COLD,
    "SE": ClimateZone.COLD,
    "FI": ClimateZone.COLD,
    "IS": ClimateZone.COLD,
    "BR": ClimateZone.HOT_HUMID,
    "NG": ClimateZone.HOT_HUMID,
    "IN": ClimateZone.HOT_HUMID,
    "SA": ClimateZone.HOT_DRY,
    "EG": ClimateZone.HOT_DRY,
    "AU": ClimateZone.HOT_DRY,  # simplified
    "ZA": ClimateZone.TEMPERATE,
    "JP": ClimateZone.TEMPERATE,
    "KR": ClimateZone.TEMPERATE,
    "CN": ClimateZone.TEMPERATE,
}


def _infer_climate(country_code: str) -> ClimateZone:
    return _COUNTRY_CLIMATE.get(country_code.upper(), ClimateZone.TEMPERATE)


# ---------------------------------------------------------------------------
# Main adapter function
# ---------------------------------------------------------------------------

def api_profile_to_formula_profile(api: ApiUserProfile) -> FormulaUserProfile:
    """
    Convert the public-facing API UserProfile into the formula engine's
    internal UserProfile model.

    Mapping rules:
    - adults, children, seniors → FamilyMember groups
    - pets → Pet list with mapped types
    - medical_needs → HealthCondition list (consent-gated)
    - duration_preference → preparation_days (days integer)
    - region.country_code → climate_zone (heuristic)
    - health_data_consent → forwarded as-is
    """
    family_members: list[FamilyMember] = []
    health_conditions = _medical_categories_to_health_conditions(
        [mn.category for mn in api.medical_needs],
        api.health_data_consent,
    )

    # Adults (18–64)
    if api.adults > 0:
        family_members.append(
            FamilyMember(
                age_group=AgeGroup.ADULT,
                count=api.adults,
                activity_level=ActivityLevel.MODERATE,
                health_conditions=health_conditions if api.health_data_consent else [],
            )
        )

    # Children (< 18)
    if api.children > 0:
        family_members.append(
            FamilyMember(
                age_group=AgeGroup.CHILD,
                count=api.children,
                activity_level=ActivityLevel.MODERATE,
                health_conditions=[],
            )
        )

    # Seniors (65+)
    if api.seniors > 0:
        family_members.append(
            FamilyMember(
                age_group=AgeGroup.SENIOR,
                count=api.seniors,
                activity_level=ActivityLevel.SEDENTARY,
                health_conditions=health_conditions if api.health_data_consent else [],
            )
        )

    # Pets
    pets: list[Pet] = []
    for pet_info in api.pets:
        pets.append(
            Pet(
                type=_map_pet_type(pet_info.type),
                count=pet_info.count,
            )
        )

    # Duration
    duration_days = DURATION_DAYS.get(
        api.duration_preference
        if isinstance(api.duration_preference, str)
        else api.duration_preference.value,
        7,  # fallback: 1 week
    )

    # Climate (inferred from country code)
    climate_zone = _infer_climate(api.region.country_code)

    return FormulaUserProfile(
        family_members=family_members,
        pets=pets,
        country=api.region.country_code,
        region=api.region.city,
        climate_zone=climate_zone,
        housing_type=HousingType.APARTMENT,  # conservative default
        preparation_days=duration_days,
        health_data_consent=api.health_data_consent,
    )
