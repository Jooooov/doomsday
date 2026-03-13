"""
Adds 30 new countries to the CountryRiskScore table.
Idempotent — skips countries already in the DB.

Run inside the container:
    docker compose exec backend python scripts/add_countries.py
"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal, init_db
from app.models.clock import CountryRiskScore
from sqlalchemy import select

# (iso2, name, seconds_to_midnight, risk_level, context_paragraph)
# Scale:  green ≥83 · yellow 70-82 · orange 63-69 · red ≤62
NEW_COUNTRIES = [
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
     "Desde o golpe militar de 2021, Myanmar vive uma guerra civil de baixa intensidade "
     "com múltiplas frentes. A junta enfrenta ofensivas coordenadas de milícias étnicas "
     "e forças de resistência pró-democracia. O colapso económico e o fluxo de refugiados "
     "afetam toda a região do Mekong."),

    ("BY", "Belarus", 58.0, "red",
     "A Bielorrússia é plataforma operacional da Rússia na Europa: albergou o Wagner Group "
     "após o motim de 2023 e é palco de exercícios nucleares táticos russos. "
     "Lukashenko eliminou oposição interna e qualquer autonomia de política externa. "
     "O risco de envolvimento direto num alargamento do conflito ucraniano é alto."),

    # ── ORANGE ──────────────────────────────────────────────────────────────
    ("IR", "Iran", 65.0, "orange",
     "O Irão acelerou o enriquecimento de urânio para 60%, a um passo da arma nuclear. "
     "A rede de proxies (Hamas, Hezbollah, Houthis, milícias iraquianas) projeta poder "
     "regional sem exposição direta. Confronto direto com Israel em abril de 2024 "
     "marcou um ponto de não retorno na escalada."),

    ("PK", "Pakistan", 66.0, "orange",
     "O Paquistão combina instabilidade política interna grave com um dos maiores arsenais "
     "nucleares do mundo (~170 ogivas). Tensões com a Índia no Caxemira, ataques do TTP "
     "e uma crise económica dependente do FMI criam um coquetel de risco sem precedentes."),

    ("YE", "Yemen", 64.0, "orange",
     "Os Houthis, apoiados pelo Irão, paralisaram o tráfego no Mar Vermelho com ataques "
     "a navios comerciais desde 2023, forçando desvios pelo Cabo da Boa Esperança. "
     "Apesar dos contra-ataques EUA/Reino Unido, a capacidade operacional Houthi "
     "permanece intacta. O conflito civil interno persiste sem solução política."),

    ("LB", "Lebanon", 65.0, "orange",
     "O Líbano saiu de um conflito de alta intensidade com Israel em 2024 com o Hezbollah "
     "enfraquecido mas não destruído. O estado libanês continua disfuncional: sem presidente, "
     "com sistema bancário colapsado e infraestrutura a reconstruir. "
     "O risco de reacendimento do conflito permanece elevado."),

    ("AF", "Afghanistan", 63.0, "orange",
     "Sob domínio Talibã, o Afeganistão voltou a ser santuário para grupos jihadistas. "
     "O ISIS-K executa ataques com alcance regional (incluindo Moscovo em 2024). "
     "O colapso do sistema de saúde, educação e economia criou uma crise humanitária "
     "que desestabiliza Paquistão, Irão e Ásia Central."),

    ("SD", "Sudan", 63.0, "orange",
     "Desde abril de 2023, o Sudão está em guerra civil entre as Forças Armadas (SAF) "
     "e as Forças de Apoio Rápido (RSF). Com mais de 8 milhões de deslocados, "
     "é a maior crise de refugiados do mundo. Khartoum foi destruída. "
     "Potências regionais (Emirados, Egito, Wagner/Rússia) alimentam os dois lados."),

    # ── YELLOW ──────────────────────────────────────────────────────────────
    ("IN", "India", 75.0, "yellow",
     "A Índia navega tensões simultâneas com China (fronteira himalaia) e Paquistão "
     "(Caxemira). Como terceira potência nuclear, qualquer escalada com Islambade "
     "tem consequências globais. O crescimento económico e a influência do Sul Global "
     "posicionam a Índia como ator pivô em qualquer rearranjo da ordem mundial."),

    ("PL", "Poland", 81.0, "yellow",
     "A Polónia tornou-se a maior potência militar convencional da Europa, com o maior "
     "orçamento de defesa da NATO em percentagem do PIB (4%). Corredor de fornecimento "
     "crítico para a Ucrânia, a Polónia está na linha da frente de qualquer alargamento "
     "do conflito para o território da Aliança."),

    ("FI", "Finland", 82.0, "yellow",
     "A Finlândia aderiu à NATO em 2023, dobrando o comprimento da fronteira da Aliança "
     "com a Rússia para 2.600 km. Com um exército de reserva de 280.000 efetivos "
     "e uma doutrina de defesa total, a Finlândia é um parceiro credível mas também "
     "um alvo de pressão russa acrescida."),

    ("EE", "Estonia", 79.0, "yellow",
     "A Estónia é o estado da NATO mais exposto à pressão russa: 25% da população "
     "é de origem russa e o país já sofreu ciberataques devastadores (2007). "
     "A presença de forças NATO batalha-grupo e o investimento em defesa cibernética "
     "são a primeira linha de contenção no Báltico."),

    ("LT", "Lithuania", 80.0, "yellow",
     "A Lituânia controla o Corredor de Suwalki, a ligação terrestre de 100km entre "
     "a Polónia e os países bálticos que separa Bielorrússia de Kaliningrado. "
     "É considerado pela NATO o ponto mais vulnerável do flanco leste — "
     "cortar este corredor seria o primeiro ato de qualquer agressão convencional."),

    ("TR", "Turkey", 74.0, "yellow",
     "A Turquia ocupa uma posição estratégica única: membro NATO que comprou o sistema "
     "de mísseis russo S-400, mediador no conflito ucraniano e controla os Estreitos. "
     "Erdogan maximiza a ambiguidade estratégica para extrair concessões tanto do Ocidente "
     "como da Rússia, tornando a Turquia um fator de imprevisibilidade sistémica."),

    ("SA", "Saudi Arabia", 72.0, "yellow",
     "A Arábia Saudita financia a normalização com Israel ao mesmo tempo que mantém "
     "relações com a China e Rússia via OPEC+. O acordo de paz com o Irão mediado "
     "pela China em 2023 foi sinal de reequilíbrio do Médio Oriente. "
     "Qualquer instabilidade no regime afeta imediatamente os mercados energéticos globais."),

    ("JP", "Japan", 80.0, "yellow",
     "O Japão reviu a Constituição Pacifista para permitir capacidades de contra-ataque "
     "e duplicou o orçamento de defesa. Confrontado com a tríade nuclear China-Rússia-Coreia "
     "do Norte, está a construir a maior força militar desde 1945. "
     "A aliança EUA-Japão é o pilar da segurança no Indo-Pacífico."),

    ("KR", "South Korea", 79.0, "yellow",
     "A Coreia do Sul enfrenta uma Coreia do Norte com arsenal nuclear crescente "
     "e mísseis hipersónicos. Pyongyang enviou munições para a Rússia, recebendo "
     "em troca tecnologia de satélites e mísseis. A Seul pesa a sua própria "
     "capacidade nuclear face à credibilidade decrescente do guarda-chuva americano."),

    ("TW", "Taiwan", 70.0, "yellow",
     "Taiwan é o principal ponto de fricção sino-americano. As incursões aéreas chinesas "
     "na ADIZ taiwanesa atingiram recordes em 2023-2024. Qualquer bloqueio ou invasão "
     "paralisaria 90% da produção global de chips avançados (TSMC). "
     "O cenário Taiwan é o maior risco de conflito entre potências nucleares do século XXI."),

    ("EG", "Egypt", 76.0, "yellow",
     "O Egito enfrenta pressões convergentes: a crise de Gaza à sua fronteira, "
     "o conflito do Sudão com fluxos de refugiados, e a disputa com a Etiópia "
     "pela Barragem do Nilo (GERD). Internamente, o peso da dívida e a inflação "
     "ameaçam a estabilidade de um estado que serve de âncora ao Médio Oriente."),

    ("NG", "Nigeria", 73.0, "yellow",
     "A Nigéria concentra múltiplas crises: Boko Haram e ISWAP no nordeste, "
     "banditismo rural no noroeste, movimentos separatistas Biafra/Oodua no sul "
     "e uma crise económica severa com inflação a 30%. Como maior economia africana, "
     "a instabilidade nigeriana tem efeitos regionais no Sahel e Golfo da Guiné."),

    ("VE", "Venezuela", 71.0, "yellow",
     "Maduro consolidou o controlo após as eleições fraudulentas de 2024, apesar "
     "da oposição de Edmundo González. A disputa territorial com a Guiana (Essequibo) "
     "escalou com exercícios militares. A migração de 7 milhões de venezuelanos "
     "desestabiliza Colômbia, Equador e o sistema de asilo regional."),

    ("MX", "Mexico", 77.0, "yellow",
     "Os cartéis mexicanos (Sinaloa, CJNG) operam como estados paralelos em regiões "
     "inteiras do país. A violência récord (35.000 homicídios/ano) coexiste com "
     "pressão americana para controlar fluxos migratórios e fentanyl. "
     "A reforma judicial de Sheinbaum gera tensões com os EUA sobre independência judiciária."),

    ("HU", "Hungary", 78.0, "yellow",
     "A Hungria de Orbán bloqueia sistematicamente consensos NATO e UE sobre a Ucrânia, "
     "mantém fluxo de gás russo e acolhe investimento chinês em baterias (BYD/CATL). "
     "É o cavalo de Tróia mais visível dentro das estruturas ocidentais, "
     "criando precedentes de veto que paralisam respostas coletivas."),

    ("SE", "Sweden", 82.0, "yellow",
     "A Suécia aderiu à NATO em março de 2024, encerrando 200 anos de neutralidade. "
     "Com uma das mais avançadas indústrias de defesa europeias (Saab/Gripen/A-26), "
     "a Suécia reforça o flanco norte da Aliança. "
     "A adaptação ao novo enquadramento estratégico decorre sem incidentes significativos."),

    # ── GREEN ────────────────────────────────────────────────────────────────
    ("AU", "Australia", 91.0, "green",
     "A Austrália aprofundou alianças de segurança via AUKUS (submarinos nucleares) "
     "e QUAD. Geograficamente distante dos principais teatros de conflito, "
     "enfrenta apenas ameaças cibernéticas e pressão económica chinesa. "
     "A maior preocupação interna é a resiliência a desastres climáticos."),

    ("CA", "Canada", 90.0, "green",
     "O Canadá beneficia de fronteiras seguras e laços profundos com os EUA via NORAD. "
     "A principal pressão é a soberania ártica face à expansão russa e às reivindicações "
     "sobre a Passagem do Noroeste. Internamente, cumpre com dificuldade a meta de 2% PIB "
     "de defesa prometida à NATO."),

    ("ES", "Spain", 91.0, "green",
     "A Espanha mantém-se fora dos principais vetores de ameaça direta, com presença "
     "NATO no Atlântico e Mediterrâneo. As cidades de Ceuta e Melilla são o único "
     "ponto de fricção regular com Marrocos. "
     "O risco terrorista jihadista (ataque de Barcelona, 2017) permanece monitorizado."),

    ("IT", "Italy", 88.0, "green",
     "A Itália alberga bases NATO e americanas críticas (Vicenza, Aviano, Nápoles) "
     "tornando-a plataforma logística importante mas também alvo potencial. "
     "A instabilidade política crónica e o peso da dívida pública limitam "
     "a capacidade de resposta autónoma a crises."),

    ("NL", "Netherlands", 84.0, "green",
     "Os Países Baixos albergam o QG da NATO, o Tribunal Internacional de Justiça e "
     "são um nó crítico de infraestrutura energética europeia (Groningen/TTF). "
     "O país aumentou o orçamento de defesa e participa na coalização de apoio à Ucrânia. "
     "O principal risco é ser alvo de sabotagem de infraestrutura crítica."),
]


async def add_countries():
    print("Initializing DB connection...")
    await init_db()

    async with AsyncSessionLocal() as db:
        existing = set(
            row[0] for row in (
                await db.execute(select(CountryRiskScore.country_iso))
            ).all()
        )
        print(f"Existing countries in DB: {len(existing)}")

        now = datetime.now(timezone.utc)
        added = 0

        for iso, name, seconds, level, ctx in NEW_COUNTRIES:
            if iso in existing:
                print(f"  SKIP {iso} — already in DB")
                continue

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
            added += 1
            print(f"  + {iso} ({name}) — {level} — {seconds}s")

        await db.commit()
        print(f"\n✅ Done! Added {added} new countries ({len(existing) + added} total).")


if __name__ == "__main__":
    asyncio.run(add_countries())
