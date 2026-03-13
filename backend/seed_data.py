"""
Seed script — populates DB with initial data for development/demo.

Inserts:
  - CountryRiskScore for 10 countries (anchored near 85s baseline)
  - NewsItem samples for Portugal and global context
  - Creates tables if they don't exist yet (via init_db)

Run inside the container:
    docker compose exec backend python seed_data.py
"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal, init_db
from app.models.clock import CountryRiskScore, NewsItem


COUNTRIES = [
    # (iso, name, seconds_to_midnight, risk_level, context_paragraph)
    ("PT", "Portugal", 95.0, "green",
     "Portugal mantém-se numa posição de baixo risco direto, beneficiando da sua localização "
     "periférica na NATO e de relações diplomáticas estáveis. A principal ameaça é indireta — "
     "perturbações económicas e energéticas derivadas de conflitos na Europa de Leste."),
    ("US", "United States", 78.0, "yellow",
     "Os EUA encontram-se em tensão elevada devido ao envolvimento em múltiplos teatros "
     "de conflito e à escalada retórica com potências nucleares. A polarização interna "
     "fragiliza a capacidade de resposta coordenada."),
    ("RU", "Russia", 62.0, "red",
     "A Rússia representa o maior fator de risco global, com guerra ativa na Ucrânia, "
     "ameaças nucleares recorrentes e isolamento diplomático crescente. O risco de "
     "escalada acidental é considerado alto."),
    ("UA", "Ukraine", 55.0, "red",
     "A Ucrânia encontra-se em estado de guerra ativa com bombardeamentos diários de "
     "infraestrutura crítica. O risco para civis é máximo nas zonas de conflito."),
    ("DE", "Germany", 88.0, "green",
     "A Alemanha enfrenta pressão crescente para aumentar capacidade de defesa e acolhe "
     "refugiados ucranianos em grande número. O risco direto é baixo mas a economia "
     "ressente-se do conflito adjacente."),
    ("FR", "France", 86.0, "green",
     "França mantém posição diplomática ativa e capacidade nuclear independente. "
     "Tensões sociais internas e ataques cibernéticos a infraestrutura são as "
     "principais preocupações no curto prazo."),
    ("GB", "United Kingdom", 83.0, "green",
     "O Reino Unido apoia ativamente a Ucrânia com armamento e inteligência. "
     "O risco direto é moderado, com potencial para ser alvo de ataques cibernéticos "
     "ou desinformação coordenada."),
    ("CN", "China", 71.0, "yellow",
     "A China mantém ambiguidade estratégica face ao conflito na Ucrânia e intensifica "
     "pressão militar sobre Taiwan. O risco de conflito no Indo-Pacífico é a maior "
     "variável de incerteza global."),
    ("IL", "Israel", 65.0, "orange",
     "Israel encontra-se em conflito ativo em Gaza com extensão para o Líbano. "
     "A possibilidade de envolvimento iraniano direto constitui o principal vetor "
     "de escalada regional."),
    ("BR", "Brazil", 92.0, "green",
     "O Brasil mantém-se fora dos principais eixos de conflito, com política externa "
     "de não-alinhamento. O risco é essencialmente indireto: pressões económicas "
     "globais e instabilidade em países vizinhos."),
]

NEWS_ITEMS = [
    {
        "headline": "NATO aumenta presença militar no flanco leste com mais 10.000 soldados",
        "source_url": "https://www.nato.int",
        "source_name": "NATO",
        "affected_countries": ["PT", "DE", "FR", "GB", "PL"],
        "impact_delta": -1.2,
    },
    {
        "headline": "Portugal reforça reservas estratégicas de combustível e alimentos",
        "source_url": "https://www.governo.pt",
        "source_name": "Governo de Portugal",
        "affected_countries": ["PT"],
        "impact_delta": 0.8,
    },
    {
        "headline": "Rússia lança ataque massivo com drones sobre infraestrutura energética ucraniana",
        "source_url": "https://www.reuters.com",
        "source_name": "Reuters",
        "affected_countries": ["UA", "RU", "DE", "PL"],
        "impact_delta": -3.5,
    },
    {
        "headline": "EUA aprovam novo pacote de ajuda militar à Ucrânia de 60 mil milhões de dólares",
        "source_url": "https://www.congress.gov",
        "source_name": "US Congress",
        "affected_countries": ["US", "UA", "RU"],
        "impact_delta": -1.8,
    },
    {
        "headline": "Exercícios militares conjuntos NATO-Portugal no Atlântico Norte",
        "source_url": "https://www.dn.pt",
        "source_name": "Diário de Notícias",
        "affected_countries": ["PT", "US", "GB"],
        "impact_delta": 0.5,
    },
    {
        "headline": "China aumenta gastos militares em 7,2% — maior aumento em 5 anos",
        "source_url": "https://www.bbc.com",
        "source_name": "BBC",
        "affected_countries": ["CN", "US", "JP", "TW"],
        "impact_delta": -2.1,
    },
    {
        "headline": "Cimeira de paz para a Ucrânia falha sem participação russa",
        "source_url": "https://www.euronews.com",
        "source_name": "Euronews",
        "affected_countries": ["UA", "RU", "DE", "FR", "US"],
        "impact_delta": -0.9,
    },
    {
        "headline": "Portugal lança campanha nacional de preparação civil — 'Esteja Preparado'",
        "source_url": "https://www.proteçãocivil.pt",
        "source_name": "Proteção Civil",
        "affected_countries": ["PT"],
        "impact_delta": 1.5,
    },
]


async def seed():
    print("Initializing database tables...")
    await init_db()

    async with AsyncSessionLocal() as db:
        # ── Check if already seeded ───────────────────────────────────────
        from sqlalchemy import select, func
        count = await db.scalar(select(func.count()).select_from(CountryRiskScore))
        if count and count > 0:
            print(f"Database already has {count} country scores — skipping seed.")
            print("To re-seed, run: docker compose exec backend python -c \"from app.core.database import AsyncSessionLocal; ...\" ")
            return

        now = datetime.now(timezone.utc)

        # ── Country risk scores ───────────────────────────────────────────
        print(f"Inserting {len(COUNTRIES)} country risk scores...")
        for iso, name, seconds, level, ctx in COUNTRIES:
            score = CountryRiskScore(
                id=str(uuid.uuid4()),
                country_iso=iso,
                seconds_to_midnight=seconds,
                risk_level=level,
                score_baseline=85.0,
                llm_context_paragraph=ctx,
                top_news_items=[],
                is_propagated=False,
                last_updated=now,
                last_scan_attempt=now,
            )
            db.add(score)

        # ── News items ────────────────────────────────────────────────────
        print(f"Inserting {len(NEWS_ITEMS)} news items...")
        for item in NEWS_ITEMS:
            news = NewsItem(
                id=str(uuid.uuid4()),
                headline=item["headline"],
                source_url=item.get("source_url"),
                source_name=item.get("source_name"),
                affected_countries=item.get("affected_countries", []),
                impact_delta=item.get("impact_delta"),
                scan_timestamp=now,
                processed=True,
            )
            db.add(news)

        await db.commit()

    print("\n✅ Seed complete!")
    print("   Countries inserted:", len(COUNTRIES))
    print("   News items inserted:", len(NEWS_ITEMS))
    print("\n   Open http://localhost:3000 to see the data.")


if __name__ == "__main__":
    asyncio.run(seed())
