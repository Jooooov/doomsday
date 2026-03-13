"""
Variable map models for the deterministic formula engine.

All inputs are strongly-typed.  The engine only accepts instances of
VariableMap and always returns ResourceResult objects — no dicts,
no free-form strings, no randomness.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ClimateZone(str, Enum):
    HOT       = "hot"        # desert, tropical dry
    TEMPERATE = "temperate"  # continental, Mediterranean
    COLD      = "cold"       # sub-arctic, mountainous
    TROPICAL  = "tropical"   # humid equatorial


class LocationType(str, Enum):
    URBAN      = "urban"
    SUBURBAN   = "suburban"
    RURAL      = "rural"
    REMOTE     = "remote"   # no road access, off-grid


class MobilityLevel(str, Enum):
    MOBILE   = "mobile"    # can evacuate on foot / vehicle
    LIMITED  = "limited"   # requires assistance
    IMMOBILE = "immobile"  # bed-bound, wheelchair


class StorageSpace(str, Enum):
    SMALL  = "small"   # flat/apartment, <5 m²
    MEDIUM = "medium"  # house, 5-20 m²
    LARGE  = "large"   # house with basement / garage, >20 m²


class FuelType(str, Enum):
    GASOLINE = "gasoline"
    DIESEL   = "diesel"
    LPG      = "lpg"
    NONE     = "none"


class PetSpecies(str, Enum):
    DOG   = "dog"
    CAT   = "cat"
    BIRD  = "bird"
    OTHER = "other"


class ThreatLevel(int, Enum):
    """
    1 = elevated monitoring
    3 = regional tension
    5 = open conflict nearby
    7 = direct threat zone
    10 = active warzone
    """
    MINIMAL  = 1
    LOW      = 2
    GUARDED  = 3
    ELEVATED = 4
    HIGH     = 5
    SEVERE   = 6
    CRITICAL = 7
    EXTREME  = 8
    IMMINENT = 9
    WARZONE  = 10


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class PetProfile(BaseModel):
    species: PetSpecies
    weight_kg: float = Field(ge=0.1, le=200.0, description="Body weight in kg")
    count: int = Field(default=1, ge=1, le=20)


class MedicationProfile(BaseModel):
    """
    One entry per chronic medication.
    daily_units is tablets/doses/ml per day per person.
    """
    name: str
    daily_units: float = Field(ge=0.0, description="Units consumed per day per person")
    unit_label: str = Field(default="tablet", description="tablet | ml | patch | etc.")
    requires_refrigeration: bool = False
    persons_count: int = Field(default=1, ge=1)


class VehicleProfile(BaseModel):
    fuel_type: FuelType = FuelType.GASOLINE
    tank_capacity_litres: float = Field(ge=0.0, le=300.0, default=50.0)
    consumption_l_per_100km: float = Field(ge=1.0, le=50.0, default=8.0)


# ---------------------------------------------------------------------------
# Main variable map
# ---------------------------------------------------------------------------

class VariableMap(BaseModel):
    """
    Complete input contract for the formula engine.

    All fields have safe defaults so callers can provide only the
    fields they know and get reasonable outputs for the rest.
    """

    # --- Household ---
    adults_count: int = Field(default=2, ge=1, le=50, description="Adults (18+)")
    children_count: int = Field(default=0, ge=0, le=20, description="Children (<18)")
    elderly_count: int = Field(default=0, ge=0, le=20, description="Elderly (65+, with higher needs)")
    infants_count: int = Field(default=0, ge=0, le=10, description="Infants (<2 years)")
    pets: List[PetProfile] = Field(default_factory=list)

    # --- Planning horizon ---
    duration_days: int = Field(default=14, ge=1, le=365, description="Days of supplies to stockpile")

    # --- Context ---
    threat_level: int = Field(default=5, ge=1, le=10, description="1 (minimal) … 10 (warzone)")
    climate_zone: ClimateZone = ClimateZone.TEMPERATE
    location_type: LocationType = LocationType.URBAN
    mobility_level: MobilityLevel = MobilityLevel.MOBILE
    storage_space: StorageSpace = StorageSpace.MEDIUM

    # --- Infrastructure ---
    has_well_water: bool = False
    has_generator: bool = False
    has_solar: bool = False
    has_wood_stove: bool = False
    vehicles: List[VehicleProfile] = Field(default_factory=list)

    # --- Health ---
    medications: List[MedicationProfile] = Field(default_factory=list)
    has_diabetic: bool = False          # affects food type guidance
    has_cardiac_patient: bool = False
    has_respiratory_patient: bool = False
    health_data_consent: bool = False   # GDPR: health data only used if True

    # --- Physical exertion expectation ---
    # Affects caloric need: 0=sedentary shelter-in-place … 1=high-exertion evacuation
    expected_exertion_factor: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("threat_level")
    @classmethod
    def clamp_threat(cls, v: int) -> int:
        return max(1, min(10, v))

    @model_validator(mode="after")
    def validate_health_consent(self) -> "VariableMap":
        """If consent not given, clear health data fields to defaults."""
        if not self.health_data_consent:
            self.medications = []
            self.has_diabetic = False
            self.has_cardiac_patient = False
            self.has_respiratory_patient = False
        return self

    @property
    def total_humans(self) -> int:
        return self.adults_count + self.children_count + self.elderly_count + self.infants_count

    @property
    def total_standard_persons(self) -> float:
        """
        Weighted person-equivalents for resource calculation.
        Infants ~0.1, children ~0.6, adults ~1.0, elderly ~0.9
        """
        return (
            self.adults_count * 1.0
            + self.children_count * 0.6
            + self.elderly_count * 0.9
            + self.infants_count * 0.1
        )


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class ResourceItem(BaseModel):
    """A single stockpile line-item."""
    name: str
    quantity: float
    unit: str
    notes: str = ""
    priority: int = Field(default=1, ge=1, le=3, description="1=critical, 2=important, 3=nice-to-have")


class CategoryResult(BaseModel):
    category: str
    items: List[ResourceItem]
    category_notes: str = ""


class ResourceResult(BaseModel):
    """
    Full output of the formula engine for one VariableMap.

    All quantities are deterministic given the same inputs.
    Formula version is stored so cached results can be invalidated
    on formula updates.
    """
    formula_version: str = "1.0.0"
    duration_days: int
    total_humans: int
    standard_persons: float
    categories: List[CategoryResult]

    @property
    def flat_items(self) -> List[ResourceItem]:
        return [item for cat in self.categories for item in cat.items]
