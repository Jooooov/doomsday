"""
Checklist Calculation API — v1

POST /api/v1/checklist/calculate
    Accepts a UserProfile payload, runs the deterministic formula engine,
    and returns a structured quantities breakdown per resource category.

Rate limiting: enforced upstream via middleware (config.RATE_LIMIT_GUIDE_PER_HOUR).
No LLM calls in this endpoint — all results are pure formula calculations.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.profile_adapter import api_profile_to_formula_profile
from app.schemas.checklist import (
    ChecklistCalculationResponse,
    DocumentsBreakdown,
    EnergyBreakdown,
    FoodBreakdown,
    MedicalBreakdown,
    PetsBreakdown,
    ProfileSummary,
    SanitationBreakdown,
    WaterBreakdown,
)
from app.schemas.profile import UserProfile as ApiUserProfile
from app.services.formula_engine import (
    ChecklistQuantities,
    DocumentsItems,
    EnergyItems,
    FoodItems,
    FormulaEngine,
    MedicalItems,
    PetItems,
    SanitationItems,
    WaterItems,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checklist", tags=["Checklist"])

# Module-level singleton (stateless, safe to share across requests)
_formula_engine = FormulaEngine()


# ---------------------------------------------------------------------------
# Dependency: rate-limit check placeholder
# (Full SlowAPI/Redis rate limiting is wired in main.py middleware;
#  this dependency is a lightweight request counter hook for future use.)
# ---------------------------------------------------------------------------

async def _check_rate_limit(request: Request) -> None:
    """
    Placeholder for per-IP rate limit validation.
    Production: use SlowAPI decorator or Redis counter in middleware.
    """
    # Actual enforcement via middleware — this is a no-op hook.
    pass


# ---------------------------------------------------------------------------
# Converters: formula engine dataclasses → Pydantic response schemas
# ---------------------------------------------------------------------------

def _water_to_schema(w: WaterItems) -> WaterBreakdown:
    return WaterBreakdown(
        drinking_water_litres=w.drinking_water_litres,
        sanitation_water_litres=w.sanitation_water_litres,
        total_water_litres=w.total_water_litres,
        water_containers_5l=w.water_containers_5l,
        water_purification_tablets=w.water_purification_tablets,
    )


def _food_to_schema(f: FoodItems) -> FoodBreakdown:
    return FoodBreakdown(
        total_calories_needed=f.total_calories_needed,
        food_kg_total=f.food_kg_total,
        rice_kg=f.rice_kg,
        canned_goods_kg=f.canned_goods_kg,
        dried_legumes_kg=f.dried_legumes_kg,
        cooking_oil_litres=f.cooking_oil_litres,
        salt_g=f.salt_g,
        sugar_g=f.sugar_g,
        infant_formula_tins=f.infant_formula_tins,
        special_dietary_notes=f.special_dietary_notes,
    )


def _medical_to_schema(m: MedicalItems) -> MedicalBreakdown:
    return MedicalBreakdown(
        first_aid_kits=m.first_aid_kits,
        bandages_rolls=m.bandages_rolls,
        antiseptic_litres=m.antiseptic_litres,
        paracetamol_tablets=m.paracetamol_tablets,
        ibuprofen_tablets=m.ibuprofen_tablets,
        oral_rehydration_sachets=m.oral_rehydration_sachets,
        prescription_medication_buffer_days=m.prescription_medication_buffer_days,
        n95_masks=m.n95_masks,
        latex_gloves_pairs=m.latex_gloves_pairs,
        thermometers=m.thermometers,
        blood_pressure_monitor=m.blood_pressure_monitor,
        glucometer=m.glucometer,
        extra_insulin_units=m.extra_insulin_units,
        pregnancy_kit=m.pregnancy_kit,
        notes=m.notes,
    )


def _sanitation_to_schema(s: SanitationItems) -> SanitationBreakdown:
    return SanitationBreakdown(
        toilet_paper_rolls=s.toilet_paper_rolls,
        soap_bars=s.soap_bars,
        hand_sanitiser_ml=s.hand_sanitiser_ml,
        garbage_bags_large=s.garbage_bags_large,
        feminine_hygiene_products=s.feminine_hygiene_products,
        diapers=s.diapers,
        baby_wipes=s.baby_wipes,
        bleach_litres=s.bleach_litres,
    )


def _energy_to_schema(e: EnergyItems) -> EnergyBreakdown:
    return EnergyBreakdown(
        candles=e.candles,
        matches_boxes=e.matches_boxes,
        flashlights=e.flashlights,
        batteries_aa=e.batteries_aa,
        batteries_aaa=e.batteries_aaa,
        power_bank_units=e.power_bank_units,
        generator_recommended=e.generator_recommended,
        fuel_litres_if_generator=e.fuel_litres_if_generator,
    )


def _documents_to_schema(d: DocumentsItems) -> DocumentsBreakdown:
    return DocumentsBreakdown(
        waterproof_document_pouch=d.waterproof_document_pouch,
        usb_drives_copies=d.usb_drives_copies,
        printed_emergency_contacts=d.printed_emergency_contacts,
        cash_minimum_eur=d.cash_minimum_eur,
    )


def _pets_to_schema(p: PetItems) -> PetsBreakdown:
    return PetsBreakdown(
        pet_food_kg=p.pet_food_kg,
        pet_water_litres=p.pet_water_litres,
        pet_medication_buffer_days=p.pet_medication_buffer_days,
        pet_carrier_units=p.pet_carrier_units,
        notes=p.notes,
    )


def _checklist_to_response(cq: ChecklistQuantities) -> ChecklistCalculationResponse:
    """Map formula engine output → API response schema."""
    summary = ProfileSummary(
        total_people=cq.total_people,
        adults=sum(
            1 for _ in range(1)  # placeholder; filled from profile below
        ),
        children=0,
        seniors=0,
        total_pets=cq.total_pets,
        preparation_days=cq.preparation_days,
        country=cq.country,
        climate_zone="temperate",   # filled per profile in the route handler
        housing_type="apartment",   # filled per profile in the route handler
        health_data_consent=False,  # filled per profile in the route handler
    )
    return ChecklistCalculationResponse(
        profile_summary=summary,
        water=_water_to_schema(cq.water),
        food=_food_to_schema(cq.food),
        medical=_medical_to_schema(cq.medical),
        sanitation=_sanitation_to_schema(cq.sanitation),
        energy=_energy_to_schema(cq.energy),
        documents=_documents_to_schema(cq.documents),
        pets=_pets_to_schema(cq.pets),
        formula_version=cq.formula_version,
    )


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------

@router.post(
    "/calculate",
    response_model=ChecklistCalculationResponse,
    status_code=status.HTTP_200_OK,
    summary="Calculate personalised checklist quantities",
    description=(
        "Accepts a household profile and returns a deterministic, "
        "per-category breakdown of survival/preparedness supply quantities. "
        "All results are formula-driven — no LLM involvement. "
        "Health data is only used when `health_data_consent` is `true` (GDPR)."
    ),
    responses={
        200: {"description": "Successful calculation"},
        422: {"description": "Validation error — invalid profile payload"},
        500: {"description": "Internal formula engine error"},
    },
)
async def calculate_checklist(
    profile: ApiUserProfile,
    _rate_limit: Annotated[None, Depends(_check_rate_limit)],
    request: Request,
) -> ChecklistCalculationResponse:
    """
    **POST /api/v1/checklist/calculate**

    Runs the deterministic formula engine against the submitted user profile
    and returns a structured quantities breakdown for each resource category:

    - **water** — drinking, sanitation, purification
    - **food** — caloric needs, food kg by type, infant formula
    - **medical** — first aid, medications, PPE, special conditions
    - **sanitation** — hygiene consumables, diapers, feminine products
    - **energy** — lighting, batteries, power banks, generator recommendation
    - **documents** — waterproof storage, cash reserves
    - **pets** — food, water, carriers

    ### GDPR note
    Health data (medications, chronic conditions) is only included in the
    calculation when `health_data_consent` is explicitly set to `true`.
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.info(
        "Checklist calculation request",
        extra={
            "client_ip": client_ip,
            "adults": profile.adults,
            "children": profile.children,
            "seniors": profile.seniors,
            "duration": profile.duration_preference,
            "country": profile.region.country_code,
            "health_consent": profile.health_data_consent,
        },
    )

    try:
        # 1. Adapt API profile → formula engine profile
        formula_profile = api_profile_to_formula_profile(profile)

        # 2. Run deterministic formula engine
        result: ChecklistQuantities = _formula_engine.calculate(formula_profile)

        # 3. Convert dataclass result → Pydantic response
        response = _checklist_to_response(result)

        # 4. Enrich the profile_summary with accurate values from the input
        response.profile_summary.adults = profile.adults
        response.profile_summary.children = profile.children
        response.profile_summary.seniors = profile.seniors
        response.profile_summary.climate_zone = formula_profile.climate_zone.value
        response.profile_summary.housing_type = formula_profile.housing_type.value
        response.profile_summary.health_data_consent = profile.health_data_consent

        logger.info(
            "Checklist calculation complete",
            extra={
                "client_ip": client_ip,
                "total_people": result.total_people,
                "preparation_days": result.preparation_days,
                "formula_version": result.formula_version,
            },
        )
        return response

    except ValueError as exc:
        logger.warning("Profile validation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected formula engine error for client %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Formula engine error — please try again.",
        ) from exc


@router.get(
    "/formula-version",
    summary="Get current formula library version",
    description="Returns the active formula version string for cache-busting purposes.",
    response_model=dict,
)
async def get_formula_version() -> dict:
    """Returns the current deterministic formula engine version."""
    return {
        "formula_version": FormulaEngine.VERSION,
        "status": "operational",
    }
