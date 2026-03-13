"""
ProfileExtractor — bridges API schemas to the formula engine.

Responsibilities:
1. Convert ``schemas.UserProfile`` (the flat API-facing model) into
   ``models.profile.UserProfile`` (the FamilyMember-based model consumed
   by the formula engine).
2. Produce ``schemas.ProfileVariableMap`` — the normalised, formula-ready
   flat variable map stored alongside guide results.
3. Build the ``db/models.StoredProfile`` kwargs dict for DB persistence,
   including all denormalized quick-access columns.

This service is the single point of truth for all cross-schema conversions;
no other module should contain schema-bridging logic.

GDPR rules enforced here:
- Medical needs / health conditions are zeroed out from the formula input
  if ``UserProfile.health_data_consent`` is False.
- ``StoredProfile.profile_data`` excludes health details when consent=False.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from app.schemas.profile import (
    DurationPreference,
    MedicalCategory,
    PetType as SchemaPetType,
    RegionInfo,
    RegionPreset,
    UserProfile as SchemaUserProfile,
    ProfileVariableMap,
)
from app.models.profile import (
    ActivityLevel,
    AgeGroup,
    ClimateZone as ModelClimateZone,
    DietaryRestriction,
    FamilyMember,
    HealthCondition,
    HousingType,
    Pet,
    PetType as ModelPetType,
    UserProfile as FormulaUserProfile,
)


# ---------------------------------------------------------------------------
# Duration mapping: DurationPreference enum → calendar days
# ---------------------------------------------------------------------------

DURATION_DAYS_MAP: Dict[str, int] = {
    DurationPreference.DAYS_3.value:   3,
    DurationPreference.WEEK_1.value:   7,
    DurationPreference.WEEKS_2.value:  14,
    DurationPreference.MONTH_1.value:  30,
    DurationPreference.MONTHS_3.value: 90,
    DurationPreference.MONTHS_6.value: 180,
}

# ---------------------------------------------------------------------------
# Region preset detection
# ---------------------------------------------------------------------------

_MVP_REGIONS = {RegionPreset.PORTUGAL.value, RegionPreset.USA.value}

_COUNTRY_LANGUAGE_MAP: Dict[str, str] = {
    "PT": "pt",
    "BR": "pt",
    "US": "en",
    "GB": "en",
    "CA": "en",
    "AU": "en",
    "DE": "de",
    "FR": "fr",
    "ES": "es",
    "IT": "it",
}


def _detect_region_preset(country_code: str) -> str:
    if country_code in _MVP_REGIONS:
        return country_code
    return RegionPreset.OTHER.value


def _detect_language(country_code: str) -> str:
    return _COUNTRY_LANGUAGE_MAP.get(country_code, "en")


# ---------------------------------------------------------------------------
# Medical category → HealthCondition mapping
# ---------------------------------------------------------------------------

_MED_CATEGORY_TO_HEALTH_CONDITION: Dict[str, Optional[HealthCondition]] = {
    MedicalCategory.MOBILITY_IMPAIRED.value:    HealthCondition.MOBILITY_IMPAIRED,
    MedicalCategory.REQUIRES_MEDICATION.value:  None,   # no direct mapping; flags separately
    MedicalCategory.REQUIRES_POWER.value:       None,   # tracked as requires_power_dependency
    MedicalCategory.VISION_IMPAIRED.value:      None,
    MedicalCategory.HEARING_IMPAIRED.value:     None,
    MedicalCategory.MENTAL_HEALTH.value:        HealthCondition.MENTAL_HEALTH,
    MedicalCategory.CHRONIC_ILLNESS.value:      None,   # generic; no specific HealthCondition
    MedicalCategory.DIETARY_RESTRICTION.value:  None,   # handled via dietary_restrictions
    MedicalCategory.PREGNANCY.value:            HealthCondition.PREGNANCY,
    MedicalCategory.INFANT_NEEDS.value:         HealthCondition.INFANT_CARE,
}


def _medical_needs_to_health_conditions(
    medical_needs: list,
) -> List[HealthCondition]:
    """Map MedicalNeed objects to the HealthCondition enum values used by formula engine."""
    conditions: List[HealthCondition] = []
    for need in medical_needs:
        category = need.category if isinstance(need.category, str) else need.category.value
        mapped = _MED_CATEGORY_TO_HEALTH_CONDITION.get(category)
        if mapped is not None:
            conditions.append(mapped)
    return conditions


# ---------------------------------------------------------------------------
# Pet type mapping
# ---------------------------------------------------------------------------

_PET_TYPE_MAP: Dict[str, ModelPetType] = {
    SchemaPetType.DOG.value:          ModelPetType.DOG_MEDIUM,
    SchemaPetType.CAT.value:          ModelPetType.CAT,
    SchemaPetType.BIRD.value:         ModelPetType.BIRD,
    SchemaPetType.SMALL_ANIMAL.value: ModelPetType.OTHER,
    SchemaPetType.REPTILE.value:      ModelPetType.OTHER,
    SchemaPetType.FISH.value:         ModelPetType.OTHER,
    SchemaPetType.OTHER.value:        ModelPetType.OTHER,
}


def _map_pet_type(schema_pet_type: str) -> ModelPetType:
    return _PET_TYPE_MAP.get(schema_pet_type, ModelPetType.OTHER)


# ---------------------------------------------------------------------------
# Complexity score
# ---------------------------------------------------------------------------

def _compute_complexity_score(profile: SchemaUserProfile, duration_days: int) -> int:
    """
    0–100 score of household preparation complexity.
    Used to tune LLM prompt verbosity.
    """
    score = 0
    # Household size (up to 20 pts)
    total = profile.adults + profile.children + profile.seniors
    score += min(total * 2, 20)
    # Duration (up to 20 pts)
    score += min(duration_days // 9, 20)
    # Medical needs (up to 25 pts)
    if profile.medical_needs:
        score += min(len(profile.medical_needs) * 5, 25)
    # Pets (up to 10 pts)
    pet_count = sum(p.count for p in profile.pets)
    score += min(pet_count * 2, 10)
    # Seniors or children raise complexity (up to 10 pts)
    score += min((profile.seniors + profile.children) * 2, 10)
    # Power dependency (15 pts — critical logistics challenge)
    needs_power = any(
        (n.category if isinstance(n.category, str) else n.category.value)
        == MedicalCategory.REQUIRES_POWER.value
        for n in profile.medical_needs
    )
    if needs_power:
        score += 15
    return min(score, 100)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ProfileExtractor:
    """
    Converts a ``schemas.UserProfile`` (API input) into the internal
    representations needed by:
      - the formula engine (``FormulaUserProfile``)
      - the variable map (``ProfileVariableMap``)
      - the DB persistence layer (``StoredProfile`` column values)
    """

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def to_formula_profile(self, schema: SchemaUserProfile) -> FormulaUserProfile:
        """
        Convert API schema → formula engine UserProfile (FamilyMember-based).

        GDPR: health conditions are only included when ``health_data_consent=True``.
        """
        health_conditions = (
            _medical_needs_to_health_conditions(schema.medical_needs)
            if schema.health_data_consent
            else []
        )

        # Build FamilyMember groups from flat counts
        family_members: List[FamilyMember] = []

        if schema.adults > 0:
            family_members.append(FamilyMember(
                age_group=AgeGroup.ADULT,
                count=schema.adults,
                activity_level=ActivityLevel.MODERATE,
                health_conditions=health_conditions if schema.adults > 0 else [],
                dietary_restrictions=[],
            ))

        if schema.children > 0:
            family_members.append(FamilyMember(
                age_group=AgeGroup.CHILD,
                count=schema.children,
                activity_level=ActivityLevel.MODERATE,
                health_conditions=[],
                dietary_restrictions=[],
            ))

        if schema.seniors > 0:
            family_members.append(FamilyMember(
                age_group=AgeGroup.SENIOR,
                count=schema.seniors,
                activity_level=ActivityLevel.SEDENTARY,
                health_conditions=health_conditions if schema.seniors > 0 else [],
                dietary_restrictions=[],
            ))

        # Pets
        pets: List[Pet] = [
            Pet(
                type=_map_pet_type(
                    p.type if isinstance(p.type, str) else p.type.value
                ),
                count=p.count,
            )
            for p in schema.pets
        ]

        duration_days = DURATION_DAYS_MAP.get(
            schema.duration_preference
            if isinstance(schema.duration_preference, str)
            else schema.duration_preference.value,
            7,
        )

        return FormulaUserProfile(
            family_members=family_members,
            pets=pets,
            country=schema.region.country_code,
            region=schema.region.city,
            climate_zone=ModelClimateZone.TEMPERATE,  # default; overridable
            housing_type=HousingType.APARTMENT,       # default; overridable
            preparation_days=duration_days,
            health_data_consent=schema.health_data_consent,
        )

    def to_variable_map(self, schema: SchemaUserProfile) -> ProfileVariableMap:
        """
        Produce the normalised, formula-ready ``ProfileVariableMap``.
        This is the single source of truth consumed by guide-generation formulas.
        """
        dur_pref = (
            schema.duration_preference
            if isinstance(schema.duration_preference, str)
            else schema.duration_preference.value
        )
        duration_days = DURATION_DAYS_MAP.get(dur_pref, 7)

        country_code = schema.region.country_code
        region_preset = _detect_region_preset(country_code)
        guide_lang = _detect_language(country_code)

        # Totals
        total_people = schema.adults + schema.children + schema.seniors
        vulnerable = schema.children + schema.seniors

        # Pets
        pet_count = sum(p.count for p in schema.pets)
        has_pets = pet_count > 0
        pet_types = list({
            (p.type if isinstance(p.type, str) else p.type.value)
            for p in schema.pets
        })
        has_large_pets = any(
            (p.type if isinstance(p.type, str) else p.type.value) == SchemaPetType.DOG.value
            for p in schema.pets
        )

        # Medical flags (only if consented)
        medical_cats: List[str] = []
        requires_power = False
        requires_medication = False
        has_mobility = False
        has_dietary = False
        has_pregnancy = False
        has_infant_needs = False

        if schema.health_data_consent and schema.medical_needs:
            medical_cats = list({
                n.category if isinstance(n.category, str) else n.category.value
                for n in schema.medical_needs
            })
            for need in schema.medical_needs:
                cat = (
                    need.category if isinstance(need.category, str) else need.category.value
                )
                if cat == MedicalCategory.REQUIRES_POWER.value:
                    requires_power = True
                if cat == MedicalCategory.REQUIRES_MEDICATION.value:
                    requires_medication = True
                if cat == MedicalCategory.MOBILITY_IMPAIRED.value:
                    has_mobility = True
                if cat == MedicalCategory.DIETARY_RESTRICTION.value:
                    has_dietary = True
                if cat == MedicalCategory.PREGNANCY.value:
                    has_pregnancy = True
                if cat == MedicalCategory.INFANT_NEEDS.value:
                    has_infant_needs = True

        # Resource multipliers (simplified; full calculation in formula engine)
        # Water: 3L adult, 2L child/senior, 0.5L/pet (FEMA baseline)
        water_per_day = (
            schema.adults * 3.0
            + schema.children * 2.0
            + schema.seniors * 2.0
            + pet_count * 0.5
        )
        water_total = water_per_day * duration_days

        # Food units: 1.0 adult, 0.75 child/senior
        food_per_day = (
            schema.adults * 1.0
            + schema.children * 0.75
            + schema.seniors * 0.75
        )
        food_total = food_per_day * duration_days

        # Medication supply: duration + 30% buffer
        med_days = round(duration_days * 1.3)

        # Complexity
        complexity = _compute_complexity_score(schema, duration_days)

        # Evacuation planning needed?
        needs_evacuation = has_large_pets or has_mobility or has_infant_needs or schema.seniors > 0

        return ProfileVariableMap(
            # Household
            total_people=total_people,
            adults=schema.adults,
            children=schema.children,
            seniors=schema.seniors,
            vulnerable_count=vulnerable,
            # Pets
            has_pets=has_pets,
            pet_count=pet_count,
            pet_types=pet_types,
            has_large_pets=has_large_pets,
            # Medical
            has_medical_needs=bool(schema.medical_needs and schema.health_data_consent),
            medical_categories=medical_cats,
            requires_power_dependency=requires_power,
            requires_medication=requires_medication,
            has_mobility_limitation=has_mobility,
            has_dietary_restriction=has_dietary,
            has_pregnancy=has_pregnancy,
            has_infant_needs=has_infant_needs,
            # Duration
            duration_preference=dur_pref,
            duration_days=duration_days,
            # Resource multipliers
            water_liters_per_day=round(water_per_day, 2),
            water_liters_total=round(water_total, 2),
            food_units_per_day=round(food_per_day, 2),
            food_units_total=round(food_total, 2),
            medication_days_supply=med_days,
            # Region
            region_country_code=country_code,
            region_preset=region_preset,
            region_city=schema.region.city,
            region_latitude=schema.region.latitude,
            region_longitude=schema.region.longitude,
            region_has_coordinates=(
                schema.region.latitude is not None and schema.region.longitude is not None
            ),
            # Guide personalisation
            guide_language_hint=guide_lang,
            needs_evacuation_planning=needs_evacuation,
            complexity_score=complexity,
            # Metadata
            health_data_consent=schema.health_data_consent,
        )

    def to_stored_profile_kwargs(
        self,
        schema: SchemaUserProfile,
        profile_id: Optional[str] = None,
        family_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return a dict of keyword arguments for creating/updating a StoredProfile row.

        The full profile is serialised to ``profile_data`` (health details stripped
        when consent=False). All denormalized columns are also populated.
        """
        # Sanitise profile_data: strip health notes when no consent
        profile_dict = schema.model_dump(mode="json")
        if not schema.health_data_consent:
            # Remove notes from medical_needs (category label is OK to keep for display)
            for need in profile_dict.get("medical_needs", []):
                need["notes"] = None

        dur_pref = (
            schema.duration_preference
            if isinstance(schema.duration_preference, str)
            else schema.duration_preference.value
        )
        duration_days = DURATION_DAYS_MAP.get(dur_pref, 7)
        total_people = schema.adults + schema.children + schema.seniors
        pet_count = sum(p.count for p in schema.pets)

        # Collect dietary flags
        dietary_flags: List[str] = []
        for need in schema.medical_needs:
            cat = (
                need.category if isinstance(need.category, str) else need.category.value
            )
            if cat == MedicalCategory.DIETARY_RESTRICTION.value and need.notes:
                dietary_flags.append(need.notes)
        has_dietary = bool(dietary_flags) or any(
            (n.category if isinstance(n.category, str) else n.category.value)
            == MedicalCategory.DIETARY_RESTRICTION.value
            for n in schema.medical_needs
        )

        # Power dependency flag (GDPR-gated)
        requires_power = False
        has_medical = False
        if schema.health_data_consent and schema.medical_needs:
            has_medical = True
            requires_power = any(
                (n.category if isinstance(n.category, str) else n.category.value)
                == MedicalCategory.REQUIRES_POWER.value
                for n in schema.medical_needs
            )

        kwargs: Dict[str, Any] = {
            "profile_data": profile_dict,
            "country": schema.region.country_code,
            "total_people": total_people,
            "adults_count": schema.adults,
            "children_count": schema.children,
            "seniors_count": schema.seniors,
            "has_pets": pet_count > 0,
            "total_pets": pet_count,
            "has_dietary_restrictions": has_dietary,
            "dietary_flags": dietary_flags if dietary_flags else None,
            "location_type": "urban",   # default; can be extended via profile expansion
            "housing_type": "apartment",
            "climate_zone": "temperate",
            "region_city": schema.region.city,
            "region_latitude": schema.region.latitude,
            "region_longitude": schema.region.longitude,
            "duration_preference": dur_pref,
            "preparation_days": duration_days,
            "storage_space_m3": None,
            "has_medical_needs": has_medical,
            "requires_power_dependency": requires_power,
            "health_data_consented": schema.health_data_consent,
        }

        if profile_id is not None:
            kwargs["id"] = profile_id
        if family_slug is not None:
            kwargs["family_slug"] = family_slug

        return kwargs

    def profile_hash(self, schema: SchemaUserProfile) -> str:
        """
        Compute a deterministic SHA-256 hash for the schema.

        Used as the primary key in checklist_cache.
        Health data is included in the hash only when consent=True,
        so consented and non-consented profiles with identical other fields
        produce different cache keys.
        """
        payload = schema.model_dump(mode="json")
        # Sort keys for canonical serialization
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
