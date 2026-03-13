"""Guide generation service — streaming + cluster cache + version rollback"""
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.guide import Guide, GuideVersion
from app.models.user import User
from app.services.llm.factory import get_llm

logger = logging.getLogger(__name__)

CATEGORIES = [
    "water", "food", "shelter", "health",
    "communication", "evacuation", "energy",
    "security", "documentation", "mental_health",
    "armed_conflict", "family_coordination",
]

GUIDE_SYSTEM_PROMPT = """You are a civil preparedness expert writing practical survival guides.
Be specific about quantities using the user's household profile.
Use metric units. Always include a brief legal disclaimer per section.
Content is informational only — not a substitute for official civil protection guidance.
Return valid JSON only."""

FALLBACK_GUIDE: dict[str, dict] = {
    "water": {
        "title": "Água",
        "items": [
            {"text": "Água engarrafada (2 litros por pessoa/dia)", "quantity": 14, "unit": "litros", "priority": 1, "formula": None},
            {"text": "Pastilhas de purificação de água", "quantity": 50, "unit": "unidades", "priority": 2, "formula": None},
            {"text": "Recipiente de armazenamento de água potável", "quantity": 1, "unit": "unidades", "priority": 2, "formula": None},
        ],
        "tips": ["Armazene pelo menos 7 dias de água potável.", "Renove o stock a cada 6 meses."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
    "food": {
        "title": "Alimentação",
        "items": [
            {"text": "Conservas (atum, feijão, tomate)", "quantity": 21, "unit": "latas", "priority": 1, "formula": None},
            {"text": "Cereais e barras energéticas", "quantity": 14, "unit": "unidades", "priority": 2, "formula": None},
            {"text": "Abre-latas manual", "quantity": 1, "unit": "unidades", "priority": 1, "formula": None},
        ],
        "tips": ["Escolha alimentos não perecíveis com longa validade.", "Tenha em conta dietas especiais do agregado."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
    "shelter": {
        "title": "Abrigo",
        "items": [
            {"text": "Sacos-cama ou mantas de emergência", "quantity": None, "unit": None, "priority": 1, "formula": None},
            {"text": "Fita adesiva larga e plástico para vedar janelas", "quantity": None, "unit": None, "priority": 2, "formula": None},
            {"text": "Ferramentas básicas (martelo, chave de fendas)", "quantity": None, "unit": None, "priority": 3, "formula": None},
        ],
        "tips": ["Identifique a divisão mais resistente da habitação.", "Saiba como desligar o gás, água e eletricidade."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
    "health": {
        "title": "Saúde",
        "items": [
            {"text": "Kit de primeiros socorros completo", "quantity": 1, "unit": "kit", "priority": 1, "formula": None},
            {"text": "Medicação habitual (reserva de 30 dias)", "quantity": 30, "unit": "dias", "priority": 1, "formula": None},
            {"text": "Luvas descartáveis e máscaras cirúrgicas", "quantity": 20, "unit": "unidades", "priority": 2, "formula": None},
        ],
        "tips": ["Mantenha os documentos de saúde acessíveis.", "Saiba prestar primeiros socorros básicos."],
        "disclaimer": "Conteúdo informativo. Não substitui aconselhamento médico profissional.",
    },
    "communication": {
        "title": "Comunicação",
        "items": [
            {"text": "Rádio a pilhas ou manivela", "quantity": 1, "unit": "unidades", "priority": 1, "formula": None},
            {"text": "Carregador solar ou banco de energia", "quantity": 1, "unit": "unidades", "priority": 2, "formula": None},
            {"text": "Lista de contactos de emergência em papel", "quantity": 1, "unit": "unidades", "priority": 1, "formula": None},
        ],
        "tips": ["Ouça a RTP ou estações locais para atualizações oficiais.", "Defina um ponto de encontro familiar."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
    "evacuation": {
        "title": "Evacuação",
        "items": [
            {"text": "Mochila de emergência (72 horas) pronta a levar", "quantity": 1, "unit": "unidades", "priority": 1, "formula": None},
            {"text": "Mapa da região em papel", "quantity": 1, "unit": "unidades", "priority": 2, "formula": None},
            {"text": "Calçado resistente e roupa sobresselente", "quantity": None, "unit": None, "priority": 2, "formula": None},
        ],
        "tips": ["Conheça as rotas de evacuação da sua área.", "Pratique o plano de evacuação com a família."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
    "energy": {
        "title": "Energia",
        "items": [
            {"text": "Lanternas e pilhas extra", "quantity": 2, "unit": "unidades", "priority": 1, "formula": None},
            {"text": "Velas e isqueiros", "quantity": 10, "unit": "unidades", "priority": 2, "formula": None},
            {"text": "Gerador portátil ou painel solar pequeno", "quantity": None, "unit": None, "priority": 3, "formula": None},
        ],
        "tips": ["Não use geradores a gasolina em espaços fechados.", "Carregue dispositivos quando houver energia disponível."],
        "disclaimer": "Conteúdo informativo. Siga as normas de segurança elétrica.",
    },
    "security": {
        "title": "Segurança",
        "items": [
            {"text": "Apito de emergência", "quantity": 1, "unit": "por pessoa", "priority": 1, "formula": None},
            {"text": "Cadeados adicionais para portas", "quantity": None, "unit": None, "priority": 2, "formula": None},
            {"text": "Colete refletor", "quantity": None, "unit": None, "priority": 3, "formula": None},
        ],
        "tips": ["Informe um familiar de confiança sobre o seu plano.", "Mantenha perfis de redes sociais privados em emergências."],
        "disclaimer": "Conteúdo informativo. Contacte as autoridades em caso de perigo.",
    },
    "documentation": {
        "title": "Documentação",
        "items": [
            {"text": "Cópias de documentos importantes (BI, passaporte, apólices)", "quantity": None, "unit": None, "priority": 1, "formula": None},
            {"text": "Pen USB encriptada com documentos digitalizados", "quantity": 1, "unit": "unidades", "priority": 2, "formula": None},
            {"text": "Dinheiro em notas pequenas", "quantity": None, "unit": None, "priority": 1, "formula": None},
        ],
        "tips": ["Guarde cópias num local seguro fora de casa.", "Inclua apólices de seguro e documentos médicos."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
    "mental_health": {
        "title": "Saúde Mental",
        "items": [
            {"text": "Jogos de tabuleiro e livros para entretenimento", "quantity": None, "unit": None, "priority": 3, "formula": None},
            {"text": "Diário ou caderno", "quantity": 1, "unit": "unidades", "priority": 3, "formula": None},
            {"text": "Brinquedos e atividades para crianças", "quantity": None, "unit": None, "priority": 2, "formula": None},
        ],
        "tips": ["Mantenha rotinas tanto quanto possível.", "Fale abertamente sobre o stress com a família."],
        "disclaimer": "Conteúdo informativo. Procure apoio psicológico profissional se necessário.",
    },
    "armed_conflict": {
        "title": "Conflito Armado",
        "items": [
            {"text": "Identificação de abrigos antideflagração na zona", "quantity": None, "unit": None, "priority": 1, "formula": None},
            {"text": "Roupa escura e neutra", "quantity": None, "unit": None, "priority": 2, "formula": None},
            {"text": "Plano de saída do país (documentos e contactos)", "quantity": None, "unit": None, "priority": 2, "formula": None},
        ],
        "tips": ["Registe-se no sistema de proteção de civis da sua embaixada.", "Afaste-se de janelas em caso de alerta."],
        "disclaimer": "Conteúdo informativo. Siga estritamente as ordens das autoridades.",
    },
    "family_coordination": {
        "title": "Coordenação Familiar",
        "items": [
            {"text": "Plano de comunicação familiar escrito", "quantity": 1, "unit": "unidades", "priority": 1, "formula": None},
            {"text": "Ponto de encontro familiar definido", "quantity": 1, "unit": "local", "priority": 1, "formula": None},
            {"text": "Responsabilidades atribuídas a cada membro", "quantity": None, "unit": None, "priority": 2, "formula": None},
        ],
        "tips": ["Pratique o plano de emergência regularmente.", "Inclua crianças e idosos no planeamento."],
        "disclaimer": "Conteúdo informativo. Siga as orientações da Proteção Civil.",
    },
}


async def _ensure_guide_in_db(user: User, cluster_hash: str, content: dict, db: AsyncSession) -> None:
    """Create Guide + GuideVersion in DB if not present (idempotent)."""
    result = await db.execute(select(Guide).where(Guide.user_id == user.id))
    guide = result.scalar_one_or_none()
    if not guide:
        guide = Guide(
            id=str(uuid.uuid4()),
            user_id=user.id,
            cluster_hash=cluster_hash,
            language=user.language,
            profile_snapshot={"country_code": user.country_code, "household_size": user.household_size},
        )
        db.add(guide)
        await db.flush()
    # Check if a version already exists
    count_res = await db.execute(select(func.count()).where(GuideVersion.guide_id == guide.id))
    if (count_res.scalar() or 0) > 0:
        return  # Already has versions
    version = GuideVersion(
        id=str(uuid.uuid4()),
        guide_id=guide.id,
        version_number=1,
        content=content,
        region_id=user.country_code,
        rollback_available=False,
    )
    db.add(version)
    await db.flush()  # flush version first to satisfy FK
    guide.current_version_id = version.id
    guide.status = "current"
    await db.commit()


def compute_cluster_hash(user: User) -> str:
    """hash(region + household_size + housing_type + language) for cache clustering."""
    key = f"{user.country_code}|{user.zip_code or ''}|{user.household_size or 1}|{user.housing_type or 'unknown'}|{user.language}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


async def get_guide_content(guide: Guide, db: AsyncSession) -> dict:
    """Load current guide content from latest version (explicit query — avoids lazy load in async)."""
    result = await db.execute(
        select(GuideVersion)
        .where(GuideVersion.guide_id == guide.id)
        .order_by(GuideVersion.version_number.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    if not latest:
        return {}
    return latest.content or {}


async def generate_guide_streaming(user: User, db: AsyncSession) -> AsyncIterator[str]:
    """Generate personalized guide section by section (streaming SSE chunks)."""
    try:
        llm = get_llm()
    except Exception as e:
        logger.warning(f"LLM unavailable, using fallback guide: {e}")
        llm = None

    cluster_hash = compute_cluster_hash(user)

    # 1. Cluster cache hit → persist to DB if needed, then return
    cache_path = Path(settings.DATA_DIR) / "clusters" / f"{cluster_hash}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            cached = json.load(f)
        # Ensure DB record exists (in case previous save failed)
        await _ensure_guide_in_db(user, cluster_hash, cached, db)
        yield json.dumps({"type": "cached", "content": cached})
        return

    # 2. Load base regional content (pre-generated batch)
    region_path = (
        Path(settings.REGIONS_DIR)
        / user.country_code.lower()
        / f"{user.zip_code or 'general'}.json"
    )
    base_content = {}
    if region_path.exists():
        with open(region_path) as f:
            base_content = json.load(f)

    content = {}

    for i, category in enumerate(CATEGORIES):
        yield json.dumps({"type": "category_start", "category": category, "index": i, "total": len(CATEGORIES)})
        if llm is None:
            section = base_content.get(category) or FALLBACK_GUIDE.get(category, {
                "title": category.replace("_", " ").title(),
                "items": [],
                "tips": [],
                "disclaimer": "Conteúdo informativo.",
            })
            content[category] = section
            yield json.dumps({"type": "category_done", "category": category, "data": section, "fallback": True})
            continue
        try:
            prompt = f"""Generate preparation guide section for: {category}
User profile:
- country={user.country_code}, language={user.language}
- household_size={user.household_size or 1}, housing={user.housing_type or 'unknown'}
- has_vehicle={user.has_vehicle}
- pets={json.dumps((user.preferences or {}).get('pet_types', []))}
- has_children={((user.preferences or {}).get('has_children', False))}, children_count={((user.preferences or {}).get('children_count', 0))}
- has_elderly={((user.preferences or {}).get('has_elderly', False))}
- has_mobility_issues={((user.preferences or {}).get('has_mobility_issues', False))}
- floor_number={((user.preferences or {}).get('floor_number', None))}
- budget_level={((user.preferences or {}).get('budget_level', 'médio'))}
Base regional content: {json.dumps(base_content.get(category, {}))}

Return JSON: {{
  "title": str,
  "items": [{{"text": str, "quantity": float|null, "unit": str|null, "priority": int, "formula": str|null}}],
  "tips": [str],
  "disclaimer": str
}}"""
            section = await llm.generate_json(prompt, GUIDE_SYSTEM_PROMPT)
            content[category] = section
            yield json.dumps({"type": "category_done", "category": category, "data": section})
        except Exception as e:
            logger.error(f"Guide generation failed for {category}: {e}")
            section = base_content.get(category) or FALLBACK_GUIDE.get(category, {
                "title": category.replace("_", " ").title(),
                "items": [],
                "tips": [],
                "disclaimer": "Conteúdo informativo.",
            })
            content[category] = section
            yield json.dumps({"type": "category_error", "category": category, "data": section})

    # 3. Persist to cluster cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    # 4. Save guide version to DB
    result = await db.execute(select(Guide).where(Guide.user_id == user.id))
    guide = result.scalar_one_or_none()

    if not guide:
        guide = Guide(
            id=str(uuid.uuid4()),
            user_id=user.id,
            cluster_hash=cluster_hash,
            language=user.language,
            profile_snapshot={
                "country_code": user.country_code,
                "household_size": user.household_size,
                "housing_type": user.housing_type,
                "has_vehicle": user.has_vehicle,
            },
        )
        db.add(guide)
        await db.flush()

    # Get next version number (explicit count — no lazy load)
    count_result = await db.execute(
        select(func.count()).where(GuideVersion.guide_id == guide.id)
    )
    next_version = (count_result.scalar() or 0) + 1

    version = GuideVersion(
        id=str(uuid.uuid4()),
        guide_id=guide.id,
        version_number=next_version,
        content=content,
        region_id=user.country_code,
        rollback_available=next_version > 1,
    )
    db.add(version)
    await db.flush()  # flush version INSERT first so FK constraint is satisfied
    guide.current_version_id = version.id
    guide.status = "current"
    await db.commit()

    yield json.dumps({"type": "complete"})


async def rollback_guide_version(user: User, region: str, db: AsyncSession) -> dict:
    """Rollback to previous guide version. CLI: rollback --region=PT --to=previous"""
    result = await db.execute(select(Guide).where(Guide.user_id == user.id))
    guide = result.scalar_one_or_none()

    if not guide:
        return {"error": "No guide found"}
    versions_res = await db.execute(
        select(GuideVersion).where(GuideVersion.guide_id == guide.id).order_by(GuideVersion.version_number)
    )
    all_versions = versions_res.scalars().all()
    if len(all_versions) < 2:
        return {"error": "No previous version available for rollback"}

    sorted_versions = list(all_versions)
    previous = sorted_versions[-2]
    guide.current_version_id = previous.id
    await db.commit()

    return {
        "rolled_back_to_version": previous.version_number,
        "region": region,
        "content_date": previous.created_at.isoformat(),
    }
