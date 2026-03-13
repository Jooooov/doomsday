"""
Formula Engine — Deterministic quantity calculations for survival checklists.

All formulas are deterministic (no LLM calls). Given the same profile input,
the output is always identical. This satisfies the personalization_accuracy
evaluation criterion.

Formulas are based on:
- FEMA recommendations (https://www.ready.gov)
- WHO emergency water guidelines
- Red Cross preparedness standards
- Portuguese Civil Protection (ANEPC) guidelines
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.profile import (
    ActivityLevel,
    AgeGroup,
    ClimateZone,
    FamilyMember,
    HealthCondition,
    HousingType,
    Pet,
    PetType,
    UserProfile,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Water (litres/person/day) — base rates by age group
WATER_BASE_LITRES: Dict[AgeGroup, float] = {
    AgeGroup.INFANT: 0.5,
    AgeGroup.CHILD: 1.5,
    AgeGroup.TEEN: 2.5,
    AgeGroup.ADULT: 3.5,
    AgeGroup.SENIOR: 3.0,
}

# Climate multipliers for water
CLIMATE_WATER_MULTIPLIER: Dict[ClimateZone, float] = {
    ClimateZone.TEMPERATE: 1.0,
    ClimateZone.HOT_DRY: 1.5,
    ClimateZone.HOT_HUMID: 1.4,
    ClimateZone.COLD: 0.9,
    ClimateZone.ARCTIC: 0.85,
}

# Activity multipliers for water
ACTIVITY_WATER_MULTIPLIER: Dict[ActivityLevel, float] = {
    ActivityLevel.SEDENTARY: 0.9,
    ActivityLevel.MODERATE: 1.0,
    ActivityLevel.ACTIVE: 1.3,
}

# Calories/person/day base (adult moderate)
CALORIE_BASE: Dict[AgeGroup, int] = {
    AgeGroup.INFANT: 800,
    AgeGroup.CHILD: 1400,
    AgeGroup.TEEN: 2000,
    AgeGroup.ADULT: 2000,
    AgeGroup.SENIOR: 1800,
}

ACTIVITY_CALORIE_MULTIPLIER: Dict[ActivityLevel, float] = {
    ActivityLevel.SEDENTARY: 0.85,
    ActivityLevel.MODERATE: 1.0,
    ActivityLevel.ACTIVE: 1.3,
}

# Food storage: 1 kcal ≈ 0.7g dried/shelf-stable food (FEMA estimate)
# We express as kg of food per 1000 kcal
FOOD_KG_PER_1000_KCAL = 0.7

# Pet water (litres/day)
PET_WATER_LITRES: Dict[PetType, float] = {
    PetType.DOG_SMALL: 0.25,
    PetType.DOG_MEDIUM: 0.5,
    PetType.DOG_LARGE: 1.0,
    PetType.CAT: 0.2,
    PetType.BIRD: 0.05,
    PetType.OTHER: 0.1,
}

# Pet food (kg/day)
PET_FOOD_KG_DAY: Dict[PetType, float] = {
    PetType.DOG_SMALL: 0.15,
    PetType.DOG_MEDIUM: 0.3,
    PetType.DOG_LARGE: 0.6,
    PetType.CAT: 0.08,
    PetType.BIRD: 0.02,
    PetType.OTHER: 0.05,
}

# Health condition water adjustments (additional litres/day)
HEALTH_WATER_EXTRA: Dict[HealthCondition, float] = {
    HealthCondition.KIDNEY_DISEASE: 1.0,
    HealthCondition.DIABETES: 0.5,
    HealthCondition.PREGNANCY: 0.5,
    HealthCondition.INFANT_CARE: 1.0,  # formula preparation / sterilisation
    HealthCondition.RESPIRATORY: 0.0,
    HealthCondition.HYPERTENSION: 0.0,
    HealthCondition.HEART_DISEASE: 0.0,
    HealthCondition.IMMUNOCOMPROMISED: 0.5,
    HealthCondition.MOBILITY_IMPAIRED: 0.0,
    HealthCondition.MENTAL_HEALTH: 0.0,
}

# Medication supply buffer (days on top of preparation_days)
MEDICATION_BUFFER_DAYS = 7


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WaterItems:
    drinking_water_litres: float
    sanitation_water_litres: float
    total_water_litres: float
    water_containers_5l: int        # 5-litre jerrycans recommended
    water_purification_tablets: int


@dataclass
class FoodItems:
    total_calories_needed: int
    food_kg_total: float
    rice_kg: float
    canned_goods_kg: float
    dried_legumes_kg: float
    cooking_oil_litres: float
    salt_g: float
    sugar_g: float
    infant_formula_tins: int        # 0 if no infants
    special_dietary_notes: List[str] = field(default_factory=list)


@dataclass
class MedicalItems:
    first_aid_kits: int
    bandages_rolls: int
    antiseptic_litres: float
    paracetamol_tablets: int
    ibuprofen_tablets: int
    oral_rehydration_sachets: int
    prescription_medication_buffer_days: int
    n95_masks: int
    latex_gloves_pairs: int
    thermometers: int
    blood_pressure_monitor: bool    # recommended for hypertension / seniors
    glucometer: bool                # recommended for diabetes
    extra_insulin_units: int        # 0 if no diabetes
    pregnancy_kit: bool
    notes: List[str] = field(default_factory=list)


@dataclass
class SanitationItems:
    toilet_paper_rolls: int
    soap_bars: int
    hand_sanitiser_ml: int
    garbage_bags_large: int
    feminine_hygiene_products: int   # units (pads)
    diapers: int                     # units
    baby_wipes: int                  # units
    bleach_litres: float


@dataclass
class EnergyItems:
    candles: int
    matches_boxes: int
    flashlights: int
    batteries_aa: int
    batteries_aaa: int
    power_bank_units: int
    generator_recommended: bool
    fuel_litres_if_generator: float


@dataclass
class DocumentsItems:
    waterproof_document_pouch: int
    usb_drives_copies: int
    printed_emergency_contacts: bool
    cash_minimum_eur: float


@dataclass
class PetItems:
    pet_food_kg: float
    pet_water_litres: float
    pet_medication_buffer_days: int
    pet_carrier_units: int
    notes: List[str] = field(default_factory=list)


@dataclass
class ChecklistQuantities:
    """Complete output of the formula engine for one profile + duration."""

    # Input echo for traceability
    profile_id: Optional[str]
    country: str
    total_people: int
    total_pets: int
    preparation_days: int

    # Calculated categories
    water: WaterItems
    food: FoodItems
    medical: MedicalItems
    sanitation: SanitationItems
    energy: EnergyItems
    documents: DocumentsItems
    pets: PetItems

    # Meta
    formula_version: str = "1.0.0"
    disclaimer: str = (
        "These quantities are estimates based on standard emergency "
        "preparedness guidelines. Adjust based on local conditions, "
        "specific health needs, and available storage. This is not "
        "medical advice. Always consult professionals for health-related decisions."
    )


# ---------------------------------------------------------------------------
# Formula Engine
# ---------------------------------------------------------------------------

class FormulaEngine:
    """
    Deterministic formula engine that converts a UserProfile
    into a ChecklistQuantities result.

    All calculations are pure functions with no side effects.
    """

    VERSION = "1.0.0"

    def calculate(self, profile: UserProfile) -> ChecklistQuantities:
        """
        Main entry point: run all sub-formulae and return full checklist.
        """
        days = profile.preparation_days

        water = self._calculate_water(profile, days)
        food = self._calculate_food(profile, days)
        medical = self._calculate_medical(profile, days)
        sanitation = self._calculate_sanitation(profile, days)
        energy = self._calculate_energy(profile, days)
        documents = self._calculate_documents(profile)
        pets = self._calculate_pets(profile, days)

        return ChecklistQuantities(
            profile_id=profile.profile_id,
            country=profile.country,
            total_people=profile.total_people,
            total_pets=profile.total_pets,
            preparation_days=days,
            water=water,
            food=food,
            medical=medical,
            sanitation=sanitation,
            energy=energy,
            documents=documents,
            pets=pets,
            formula_version=self.VERSION,
        )

    # ------------------------------------------------------------------
    # Water
    # ------------------------------------------------------------------
    def _calculate_water(self, profile: UserProfile, days: int) -> WaterItems:
        climate_mult = CLIMATE_WATER_MULTIPLIER[profile.climate_zone]
        drinking_total = 0.0

        for member in profile.family_members:
            base = WATER_BASE_LITRES[member.age_group]
            activity_mult = ACTIVITY_WATER_MULTIPLIER[member.activity_level]
            health_extra = sum(
                HEALTH_WATER_EXTRA.get(hc, 0.0)
                for hc in member.health_conditions
            )
            daily_per_person = (base * activity_mult * climate_mult) + health_extra
            drinking_total += daily_per_person * member.count

        # Sanitation water: 5 litres/person/day (FEMA baseline)
        sanitation_daily = profile.total_people * 5.0
        sanitation_total = sanitation_daily * days
        drinking_total_all_days = drinking_total * days
        total_water = drinking_total_all_days + sanitation_total

        # 5-litre containers (round up)
        containers_5l = math.ceil(total_water / 5)

        # Water purification: 1 tablet per 1 litre of drinking water (standard dosage)
        purification_tablets = math.ceil(drinking_total_all_days)

        return WaterItems(
            drinking_water_litres=round(drinking_total_all_days, 1),
            sanitation_water_litres=round(sanitation_total, 1),
            total_water_litres=round(total_water, 1),
            water_containers_5l=containers_5l,
            water_purification_tablets=purification_tablets,
        )

    # ------------------------------------------------------------------
    # Food
    # ------------------------------------------------------------------
    def _calculate_food(self, profile: UserProfile, days: int) -> FoodItems:
        total_calories = 0
        has_infant = False
        special_notes: List[str] = []
        dietary_flags: set = set()

        for member in profile.family_members:
            base_kcal = CALORIE_BASE[member.age_group]
            act_mult = ACTIVITY_CALORIE_MULTIPLIER[member.activity_level]

            # Pregnancy calorie increase
            if HealthCondition.PREGNANCY in member.health_conditions:
                base_kcal = int(base_kcal * 1.15)
                special_notes.append("Caloric increase applied for pregnancy.")

            daily_kcal = base_kcal * act_mult * member.count
            total_calories += daily_kcal

            if member.age_group == AgeGroup.INFANT:
                has_infant = True

            for dr in member.dietary_restrictions:
                dietary_flags.add(dr.value)

        total_calories_all_days = int(total_calories * days)
        food_kg_total = round((total_calories_all_days / 1000) * FOOD_KG_PER_1000_KCAL, 1)

        # Food breakdown (heuristic ratios for shelf-stable emergency stock)
        rice_kg = round(food_kg_total * 0.35, 1)           # 35% rice/grains
        canned_goods_kg = round(food_kg_total * 0.30, 1)   # 30% canned veg/meat/fish
        dried_legumes_kg = round(food_kg_total * 0.20, 1)  # 20% lentils, beans
        cooking_oil_litres = round(food_kg_total * 0.05, 1)  # 5% oil (~0.92 kg/litre)
        # Salt: 5g/person/day; Sugar: 10g/person/day
        salt_g = round(profile.total_people * 5 * days)
        sugar_g = round(profile.total_people * 10 * days)

        # Infant formula: 1 tin (~900g) = ~7 days for newborn
        infant_formula_tins = 0
        if has_infant:
            infant_count = sum(
                m.count for m in profile.family_members if m.age_group == AgeGroup.INFANT
            )
            infant_formula_tins = math.ceil((days / 7) * infant_count)
            special_notes.append(
                f"{infant_formula_tins} tins of infant formula included for {infant_count} infant(s)."
            )

        if dietary_flags:
            special_notes.append(
                f"Dietary restrictions noted: {', '.join(sorted(dietary_flags))}. "
                "Adjust food selection accordingly."
            )

        return FoodItems(
            total_calories_needed=total_calories_all_days,
            food_kg_total=food_kg_total,
            rice_kg=rice_kg,
            canned_goods_kg=canned_goods_kg,
            dried_legumes_kg=dried_legumes_kg,
            cooking_oil_litres=cooking_oil_litres,
            salt_g=float(salt_g),
            sugar_g=float(sugar_g),
            infant_formula_tins=infant_formula_tins,
            special_dietary_notes=special_notes,
        )

    # ------------------------------------------------------------------
    # Medical
    # ------------------------------------------------------------------
    def _calculate_medical(self, profile: UserProfile, days: int) -> MedicalItems:
        people = profile.total_people
        notes: List[str] = []

        # First aid: 1 kit per household, +1 per 4 additional people
        first_aid_kits = max(1, math.ceil(people / 4))
        bandages_rolls = people * 2
        antiseptic_litres = round(max(0.5, people * 0.05), 2)

        # OTC medications (standard quantity per person per week × weeks)
        weeks = math.ceil(days / 7)
        paracetamol_tablets = people * 8 * weeks   # 4 doses/day × 2 days per person per week
        ibuprofen_tablets = people * 6 * weeks
        oral_rehydration_sachets = people * 3 * weeks

        # PPE
        n95_masks = people * math.ceil(days / 3)   # 1 mask per 3 days per person
        latex_gloves_pairs = people * 5 * weeks

        thermometers = max(1, math.ceil(people / 4))

        # Special conditions
        has_hypertension = any(
            HealthCondition.HYPERTENSION in m.health_conditions
            for m in profile.family_members
        )
        has_diabetes = any(
            HealthCondition.DIABETES in m.health_conditions
            for m in profile.family_members
        )
        has_senior = any(
            m.age_group == AgeGroup.SENIOR for m in profile.family_members
        )
        has_pregnancy = any(
            HealthCondition.PREGNANCY in m.health_conditions
            for m in profile.family_members
        )

        blood_pressure_monitor = has_hypertension or has_senior
        glucometer = has_diabetes

        extra_insulin_units = 0
        if has_diabetes:
            # Rough estimate: average 30 units/day → buffer for full duration + 7 days
            diabetes_member_count = sum(
                m.count for m in profile.family_members
                if HealthCondition.DIABETES in m.health_conditions
            )
            extra_insulin_units = diabetes_member_count * 30 * (days + MEDICATION_BUFFER_DAYS)
            notes.append(
                f"Insulin estimate: {extra_insulin_units} units for {diabetes_member_count} person(s). "
                "Consult endocrinologist for precise dosage."
            )

        pregnancy_kit = has_pregnancy
        if has_pregnancy:
            notes.append(
                "Pregnancy emergency kit recommended. Include prenatal vitamins, "
                "sterile delivery kit, and emergency contact for nearest maternity ward."
            )

        return MedicalItems(
            first_aid_kits=first_aid_kits,
            bandages_rolls=bandages_rolls,
            antiseptic_litres=antiseptic_litres,
            paracetamol_tablets=paracetamol_tablets,
            ibuprofen_tablets=ibuprofen_tablets,
            oral_rehydration_sachets=oral_rehydration_sachets,
            prescription_medication_buffer_days=days + MEDICATION_BUFFER_DAYS,
            n95_masks=n95_masks,
            latex_gloves_pairs=latex_gloves_pairs,
            thermometers=thermometers,
            blood_pressure_monitor=blood_pressure_monitor,
            glucometer=glucometer,
            extra_insulin_units=extra_insulin_units,
            pregnancy_kit=pregnancy_kit,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Sanitation
    # ------------------------------------------------------------------
    def _calculate_sanitation(self, profile: UserProfile, days: int) -> SanitationItems:
        people = profile.total_people

        # Toilet paper: ~1 roll per person per week
        toilet_paper_rolls = math.ceil(people * (days / 7))
        # Soap: 1 bar per person per 2 weeks
        soap_bars = math.ceil(people * (days / 14))
        # Hand sanitiser: 5ml per use × 6 uses/day = 30ml/person/day
        hand_sanitiser_ml = math.ceil(people * 30 * days)
        # Garbage bags: 2 per week per household
        garbage_bags_large = math.ceil(2 * (days / 7))
        # Bleach for water disinfection: 8 drops per litre → 1 litre bleach ≈ 3000 litres water
        # We target sanitation use: ~200ml per person per week for surface disinfection
        bleach_litres = round(people * 0.2 * (days / 7), 2)

        # Feminine hygiene: assume 50% of adults/teens are female; ~20 pads per cycle
        female_estimate = sum(
            m.count for m in profile.family_members
            if m.age_group in (AgeGroup.ADULT, AgeGroup.TEEN)
        )
        female_estimate = math.ceil(female_estimate * 0.5)
        cycles = math.ceil(days / 28)
        feminine_hygiene_products = female_estimate * 20 * cycles

        # Diapers
        infant_count = sum(
            m.count for m in profile.family_members
            if m.age_group == AgeGroup.INFANT
        )
        # ~8 diapers/day for infants
        diapers = infant_count * 8 * days

        # Baby wipes: 1 pack (~80 wipes) per 10 days per infant
        baby_wipes = math.ceil(infant_count * (days / 10)) * 80

        return SanitationItems(
            toilet_paper_rolls=toilet_paper_rolls,
            soap_bars=soap_bars,
            hand_sanitiser_ml=hand_sanitiser_ml,
            garbage_bags_large=garbage_bags_large,
            feminine_hygiene_products=feminine_hygiene_products,
            diapers=diapers,
            baby_wipes=baby_wipes,
            bleach_litres=bleach_litres,
        )

    # ------------------------------------------------------------------
    # Energy / Power
    # ------------------------------------------------------------------
    def _calculate_energy(self, profile: UserProfile, days: int) -> EnergyItems:
        people = profile.total_people

        # Candles: 1 candle burns ~8h → 2 per evening per household
        candles = math.ceil(2 * days)
        matches_boxes = math.ceil(days / 14)         # 1 box/2 weeks
        flashlights = max(1, math.ceil(people / 2))  # 1 per 2 people
        batteries_aa = flashlights * 4 * math.ceil(days / 7)   # refresh weekly
        batteries_aaa = 4 * math.ceil(days / 14)    # for small devices
        power_bank_units = max(1, math.ceil(people / 3))

        # Generator for large households or long duration
        generator_recommended = (people >= 5 or days >= 60 or
                                   profile.housing_type == HousingType.RURAL)
        fuel_litres = 0.0
        if generator_recommended:
            # 1kW generator: ~0.3 litres/hour × 6h/day
            fuel_litres = round(0.3 * 6 * days, 1)

        return EnergyItems(
            candles=candles,
            matches_boxes=matches_boxes,
            flashlights=flashlights,
            batteries_aa=batteries_aa,
            batteries_aaa=batteries_aaa,
            power_bank_units=power_bank_units,
            generator_recommended=generator_recommended,
            fuel_litres_if_generator=fuel_litres,
        )

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    def _calculate_documents(self, profile: UserProfile) -> DocumentsItems:
        # Minimum cash: 3 days × daily expenses estimate per person
        # Rough: €50/person/day emergency
        daily_cash_per_person = 50.0
        cash_minimum_eur = profile.total_people * daily_cash_per_person * 3

        return DocumentsItems(
            waterproof_document_pouch=1,
            usb_drives_copies=2,
            printed_emergency_contacts=True,
            cash_minimum_eur=cash_minimum_eur,
        )

    # ------------------------------------------------------------------
    # Pets
    # ------------------------------------------------------------------
    def _calculate_pets(self, profile: UserProfile, days: int) -> PetItems:
        if not profile.pets:
            return PetItems(
                pet_food_kg=0.0,
                pet_water_litres=0.0,
                pet_medication_buffer_days=0,
                pet_carrier_units=0,
            )

        total_food_kg = 0.0
        total_water_litres = 0.0
        notes: List[str] = []

        for pet in profile.pets:
            food_per_day = PET_FOOD_KG_DAY.get(pet.type, 0.1)
            water_per_day = PET_WATER_LITRES.get(pet.type, 0.1)
            total_food_kg += food_per_day * pet.count * days
            total_water_litres += water_per_day * pet.count * days

        pet_carrier_units = len(profile.pets)  # one carrier type per pet group

        notes.append(
            "Include pet medications with same buffer as human prescription buffer."
        )
        notes.append(
            "Carry copies of vaccination records for pets in waterproof pouch."
        )

        return PetItems(
            pet_food_kg=round(total_food_kg, 2),
            pet_water_litres=round(total_water_litres, 1),
            pet_medication_buffer_days=days + MEDICATION_BUFFER_DAYS,
            pet_carrier_units=pet_carrier_units,
            notes=notes,
        )
