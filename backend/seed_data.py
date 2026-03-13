"""
Seed script — populates DB with initial data for development/demo.

Inserts:
  - CountryRiskScore for 41 countries (anchored near 85s baseline, scale: green≥83 · yellow70-82 · orange63-69 · red≤62)
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
    # Scale:  green ≥83 · yellow 70-82 · orange 63-69 · red ≤62
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

    # ── RED ─────────────────────────────────────────────────────────────────
    ("KP", "North Korea", 45.0, "red",
     "A Coreia do Norte representa o nó mais imprevisível do sistema nuclear global. "
     "Testes de mísseis balísticos intercontinentais e a doutrina de primeiro ataque "
     "nuclear tornaram qualquer cálculo de dissuasão altamente incerto. "
     "A transferência de tecnologia para Rússia e Irão amplifica o risco regional."),
    ("SY", "Syria", 52.0, "red",
     "A Síria permanece um estado fragmentado com múltiplas forças estrangeiras em solo. "
     "O colapso do regime Assad em 2024 abriu espaço a grupos jihadistas como HTS no norte. "
     "A presença simultânea de forças turcas, curdas, israelitas e iranianas cria "
     "condições para incidentes de escalada acidental."),
    ("MM", "Myanmar", 54.0, "red",
     "Desde o golpe militar de 2021, Myanmar vive uma guerra civil com múltiplas frentes. "
     "A junta enfrenta ofensivas de milícias étnicas e forças de resistência pró-democracia. "
     "O colapso económico e o fluxo de refugiados afetam toda a região do Mekong."),
    ("BY", "Belarus", 58.0, "red",
     "A Bielorrússia é plataforma operacional da Rússia na Europa: albergou o Wagner Group "
     "e é palco de exercícios nucleares táticos russos. Lukashenko eliminou a oposição "
     "interna. O risco de envolvimento direto num alargamento do conflito ucraniano é alto."),

    # ── ORANGE ──────────────────────────────────────────────────────────────
    ("IR", "Iran", 65.0, "orange",
     "O Irão acelerou o enriquecimento de urânio para 60%. A rede de proxies (Hamas, "
     "Hezbollah, Houthis) projeta poder regional sem exposição direta. "
     "O confronto direto com Israel em 2024 marcou um ponto de não retorno na escalada."),
    ("PK", "Pakistan", 66.0, "orange",
     "O Paquistão combina instabilidade política grave com um dos maiores arsenais "
     "nucleares (~170 ogivas). Tensões com a Índia no Caxemira, ataques do TTP "
     "e uma crise económica dependente do FMI criam um coquetel de risco sem precedentes."),
    ("YE", "Yemen", 64.0, "orange",
     "Os Houthis paralisaram o tráfego no Mar Vermelho com ataques a navios comerciais, "
     "forçando desvios pelo Cabo da Boa Esperança. O conflito civil interno persiste "
     "sem solução política e a capacidade operacional Houthi permanece intacta."),
    ("LB", "Lebanon", 65.0, "orange",
     "O Líbano saiu de um conflito de alta intensidade com Israel com o Hezbollah "
     "enfraquecido mas não destruído. O estado libanês continua disfuncional: "
     "sem presidente, com sistema bancário colapsado e infraestrutura a reconstruir."),
    ("AF", "Afghanistan", 63.0, "orange",
     "Sob domínio Talibã, o Afeganistão voltou a ser santuário para grupos jihadistas. "
     "O ISIS-K executa ataques com alcance regional. O colapso económico e humanitário "
     "desestabiliza Paquistão, Irão e a Ásia Central."),
    ("SD", "Sudan", 63.0, "orange",
     "Desde 2023, o Sudão está em guerra civil entre as Forças Armadas e as RSF. "
     "Com mais de 8 milhões de deslocados, é a maior crise de refugiados do mundo. "
     "Potências regionais (Emirados, Egito, Wagner/Rússia) alimentam os dois lados."),

    # ── YELLOW ──────────────────────────────────────────────────────────────
    ("IN", "India", 75.0, "yellow",
     "A Índia navega tensões com China (fronteira himalaia) e Paquistão (Caxemira). "
     "Como terceira potência nuclear, qualquer escalada com Islamabad tem consequências "
     "globais. A sua influência no Sul Global torna-a ator pivô na nova ordem mundial."),
    ("PL", "Poland", 81.0, "yellow",
     "A Polónia é a maior potência militar convencional da Europa, com o maior "
     "orçamento de defesa da NATO em % do PIB (4%). Corredor de fornecimento crítico "
     "para a Ucrânia, está na linha da frente de qualquer alargamento do conflito."),
    ("FI", "Finland", 82.0, "yellow",
     "A Finlândia aderiu à NATO em 2023, dobrando a fronteira da Aliança com a Rússia "
     "para 2.600 km. Com um exército de reserva de 280.000 efetivos e doutrina de "
     "defesa total, é parceiro credível mas alvo de pressão russa acrescida."),
    ("EE", "Estonia", 79.0, "yellow",
     "A Estónia é o estado NATO mais exposto à pressão russa: 25% da população é "
     "de origem russa e o país já sofreu ciberataques devastadores (2007). "
     "A presença de forças NATO batalha-grupo é a primeira linha de contenção no Báltico."),
    ("LT", "Lithuania", 80.0, "yellow",
     "A Lituânia controla o Corredor de Suwalki, a ligação terrestre de 100km entre "
     "Polónia e países bálticos. É considerado pela NATO o ponto mais vulnerável "
     "do flanco leste — cortar este corredor seria o primeiro ato de qualquer agressão."),
    ("TR", "Turkey", 74.0, "yellow",
     "A Turquia é membro NATO que comprou o S-400 russo e medeia o conflito ucraniano. "
     "Controla os Estreitos do Bósforo e maximiza a ambiguidade estratégica para "
     "extrair concessões de todos os lados, tornando-se fator de imprevisibilidade."),
    ("SA", "Saudi Arabia", 72.0, "yellow",
     "A Arábia Saudita aproxima-se de Israel enquanto mantém relações com China e Rússia. "
     "O acordo de paz com o Irão mediado pela China sinalizou reequilíbrio no Médio Oriente. "
     "Qualquer instabilidade no regime afeta imediatamente os mercados energéticos globais."),
    ("JP", "Japan", 80.0, "yellow",
     "O Japão reviu a Constituição Pacifista e duplicou o orçamento de defesa. "
     "Confrontado com a tríade China-Rússia-Coreia do Norte, está a construir "
     "a maior força militar desde 1945. A aliança EUA-Japão ancora a segurança no Indo-Pacífico."),
    ("KR", "South Korea", 79.0, "yellow",
     "A Coreia do Sul enfrenta uma Coreia do Norte com arsenal nuclear crescente. "
     "Pyongyang enviou munições para a Rússia em troca de tecnologia de mísseis. "
     "Seul pondera a sua própria capacidade nuclear face ao guarda-chuva americano."),
    ("TW", "Taiwan", 70.0, "yellow",
     "Taiwan é o principal ponto de fricção sino-americano. Qualquer bloqueio ou invasão "
     "paralisaria 90% da produção global de chips avançados (TSMC). "
     "É o maior risco de conflito entre potências nucleares do século XXI."),
    ("EG", "Egypt", 76.0, "yellow",
     "O Egito enfrenta a crise de Gaza à sua fronteira, o conflito do Sudão com fluxos "
     "de refugiados e a disputa com a Etiópia pela Barragem do Nilo (GERD). "
     "É âncora regional cujo colapso teria consequências para todo o Médio Oriente."),
    ("NG", "Nigeria", 73.0, "yellow",
     "A Nigéria concentra Boko Haram no nordeste, banditismo rural no noroeste, "
     "movimentos separatistas no sul e inflação a 30%. Como maior economia africana, "
     "a sua instabilidade afeta toda a região do Sahel e Golfo da Guiné."),
    ("VE", "Venezuela", 71.0, "yellow",
     "Maduro consolidou o controlo após eleições fraudulentas em 2024. A disputa "
     "territorial com a Guiana (Essequibo) escalou com exercícios militares. "
     "A migração de 7 milhões de venezuelanos desestabiliza toda a América do Sul."),
    ("MX", "Mexico", 77.0, "yellow",
     "Os cartéis mexicanos operam como estados paralelos em regiões inteiras do país. "
     "A violência recorde coexiste com pressão americana sobre fluxos migratórios e fentanyl. "
     "A reforma judicial gera tensões com os EUA sobre independência judiciária."),
    ("HU", "Hungary", 78.0, "yellow",
     "A Hungria de Orbán bloqueia consensos NATO e UE sobre a Ucrânia, mantém gás russo "
     "e acolhe investimento chinês. É o cavalo de Tróia mais visível nas estruturas "
     "ocidentais, criando precedentes de veto que paralisam respostas coletivas."),
    ("SE", "Sweden", 82.0, "yellow",
     "A Suécia aderiu à NATO em 2024, encerrando 200 anos de neutralidade. "
     "Com uma das mais avançadas indústrias de defesa europeias (Saab/Gripen), "
     "reforça o flanco norte da Aliança Atlantic."),

    # ── GREEN ────────────────────────────────────────────────────────────────
    ("AU", "Australia", 91.0, "green",
     "A Austrália aprofundou alianças via AUKUS (submarinos nucleares) e QUAD. "
     "Geograficamente distante dos conflitos, enfrenta principalmente ameaças cibernéticas "
     "e pressão económica chinesa. A maior vulnerabilidade são os desastres climáticos."),
    ("CA", "Canada", 90.0, "green",
     "O Canadá beneficia de fronteiras seguras e laços com os EUA via NORAD. "
     "A principal pressão é a soberania ártica face à expansão russa. "
     "Cumpre com dificuldade a meta de 2% PIB de defesa prometida à NATO."),
    ("ES", "Spain", 91.0, "green",
     "A Espanha mantém-se fora dos principais vetores de ameaça direta. "
     "As cidades de Ceuta e Melilla são o único ponto de fricção com Marrocos. "
     "O risco terrorista jihadista permanece monitorizado pelos serviços de segurança."),
    ("IT", "Italy", 88.0, "green",
     "A Itália alberga bases NATO e americanas críticas (Vicenza, Aviano, Nápoles). "
     "A instabilidade política crónica e o peso da dívida pública limitam "
     "a capacidade de resposta autónoma a crises regionais."),
    ("NL", "Netherlands", 84.0, "green",
     "Os Países Baixos albergam o QG da NATO e o Tribunal Internacional de Justiça. "
     "O principal risco é ser alvo de sabotagem de infraestrutura crítica "
     "(oleodutos, cabos submarinos, nós logísticos do porto de Roterdão)."),
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
