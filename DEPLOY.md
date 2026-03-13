# Plano de Deploy — Doomsday Prep Platform
**Opção A: VPS Hetzner + Docker Compose + Nginx + Let's Encrypt**

---

## Visão Geral

```
Utilizadores
     │ HTTPS
     ▼
┌─────────────┐
│  Nginx:443  │  reverse proxy + SSL termination
└──────┬──────┘
       │
  ┌────┴────┐
  │         │
  ▼         ▼
Frontend  Backend
:3000     :8000
(Next.js) (FastAPI)
            │
      ┌─────┴─────┐
      ▼           ▼
  Postgres     Redis
   :5432        :6379
```

**Custo estimado:** €3.79–€5.39/mês (Hetzner CX22 ou CX32)
**Região:** Hetzner Falkenstein (EU, GDPR compliant, baixa latência para PT)

---

## Pré-requisitos (o que precisas antes de começar)

### 1. Domínio
- [ ] Comprar/ter um domínio (ex: `doomsdayprep.pt` ou `prepara.pt`)
- [ ] Apontar DNS → IP do servidor (registo `A`)
- [ ] TTL baixo (300s) para o DNS propagar rápido no início

### 2. Contas necessárias
- [ ] [Hetzner Cloud](https://console.hetzner.cloud) — para o servidor
- [ ] GitHub — já existe (`Jooooov/doomsday`)
- [ ] (Opcional) [Cloudflare](https://cloudflare.com) — para DNS + protecção DDoS grátis

### 3. Chaves SSH
```bash
# Gera par de chaves (se não tens)
ssh-keygen -t ed25519 -C "doomsday-deploy" -f ~/.ssh/doomsday_deploy

# Copia a pública para o Hetzner durante a criação do servidor
cat ~/.ssh/doomsday_deploy.pub
```

---

## Fase 1 — Servidor

### 1.1 Criar VPS no Hetzner
- **Tipo:** CX22 (2 vCPU, 4GB RAM, 40GB SSD) — €3.79/mês
- **OS:** Ubuntu 22.04 LTS
- **Região:** Falkenstein (EU)
- **SSH Key:** adicionar a chave pública gerada acima
- **Firewall:** criar regras (ver abaixo)

### 1.2 Firewall Hetzner (criar antes de fazer deploy)
| Porta | Protocolo | Origem | Para quê |
|-------|-----------|--------|----------|
| 22 | TCP | O teu IP | SSH |
| 80 | TCP | Anywhere | HTTP (redireciona para HTTPS) |
| 443 | TCP | Anywhere | HTTPS |

> ⚠️ Porta 8000 e 3000 **não devem estar expostas** — ficam internas ao Docker.

---

## Fase 2 — Domínio & DNS

### 2.1 Configuração DNS (no teu registrar ou Cloudflare)
```
A     @          <IP do servidor>     TTL 300
A     www        <IP do servidor>     TTL 300
```

### 2.2 (Recomendado) Cloudflare em frente
- Mudar os nameservers para Cloudflare
- Vantagens: protecção DDoS grátis, cache, analytics, proxied HTTPS
- Manter SSL mode em **"Full (strict)"** quando o servidor já tiver cert

---

## Fase 3 — Variáveis de Ambiente

### 3.1 Gerar valores para produção
```bash
# Secret key JWT (corre no teu Mac)
openssl rand -hex 32

# VAPID keys para push notifications
cd /Users/joaovicente/Desktop/apps/doomsday/backend
python scripts/generate_vapid.py
```

### 3.2 Ficheiro `.env` de produção (guardar em local seguro, nunca no git)
```env
# ── Base de dados ────────────────────────────────────
POSTGRES_USER=doomsday
POSTGRES_PASSWORD=<password forte gerado>
DATABASE_URL=postgresql+asyncpg://doomsday:<password>@postgres:5432/doomsday

# ── Redis ────────────────────────────────────────────
REDIS_URL=redis://redis:6379

# ── Auth ─────────────────────────────────────────────
SECRET_KEY=<openssl rand -hex 32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# ── CORS ─────────────────────────────────────────────
CORS_ORIGINS=["https://teudominio.com","https://www.teudominio.com"]

# ── Frontend ─────────────────────────────────────────
NEXT_PUBLIC_API_URL=https://teudominio.com
NEXT_PUBLIC_VAPID_PUBLIC_KEY=<vapid public key>

# ── Push Notifications ───────────────────────────────
VAPID_PRIVATE_KEY=<vapid private key>
VAPID_PUBLIC_KEY=<vapid public key>
VAPID_CLAIMS_EMAIL=teu@email.com

# ── LLM (opcional — funciona sem isto com fallback) ──
LLM_PROVIDER=ollama
LLM_MODEL=qwen3.5:35b-a3b
LLM_BASE_URL=http://host.docker.internal:11434

# ── Google OAuth (opcional) ──────────────────────────
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# ── News API (opcional) ──────────────────────────────
NEWS_API_KEY=

# ── Cloudflare Pages fallback (opcional) ─────────────
CF_ACCOUNT_ID=
CF_API_TOKEN=
CF_PAGES_PROJECT=doomsday-fallback

# ── Rate limiting ────────────────────────────────────
GUIDE_RATE_LIMIT_PER_HOUR=5
GUIDE_RATE_LIMIT_WINDOW=3600

# ── Doomsday Clock ───────────────────────────────────
CLOCK_SCAN_INTERVAL_HOURS=6
CLOCK_ANCHOR_SECONDS=85
GDELT_ENABLED=true
```

### 3.3 GitHub Secrets (para CI/CD automático)
Ir a: `GitHub → Jooooov/doomsday → Settings → Secrets and variables → Actions`

| Secret | Valor |
|--------|-------|
| `VPS_HOST` | IP do servidor Hetzner |
| `VPS_USER` | `root` |
| `VPS_SSH_KEY` | Conteúdo de `~/.ssh/doomsday_deploy` (chave **privada**) |
| `PROD_ENV` | Conteúdo completo do `.env` de produção |

---

## Fase 4 — Deploy Inicial

### 4.1 Bootstrap do servidor (1 único comando)
```bash
ssh root@<IP_DO_SERVIDOR>

bash <(curl -s https://raw.githubusercontent.com/Jooooov/doomsday/main/scripts/setup-vps.sh) \
  teudominio.com \
  teu@email.com
```

O script faz automaticamente:
- Instala Docker, UFW, certbot
- Clona o repositório para `/opt/doomsday`
- Configura firewall (ports 80/443/22)
- Obtém certificado SSL Let's Encrypt
- Configura cron de renovação automática
- Substitui `DOMAIN_PLACEHOLDER` no nginx.conf

### 4.2 Copiar `.env` para o servidor
```bash
scp /caminho/local/.env.prod root@<IP>:/opt/doomsday/.env
```

### 4.3 Primeiro deploy
```bash
ssh root@<IP>
cd /opt/doomsday
docker compose -f docker-compose.prod.yml up -d --build

# Aguarda ~2 minutos e verifica
docker compose -f docker-compose.prod.yml ps
docker logs doomsday-backend --tail 20
```

### 4.4 Seed da base de dados (só na primeira vez)
```bash
docker exec doomsday-backend sh -c "cd /app && PYTHONPATH=/app python seed_data.py"
docker exec doomsday-backend sh -c "cd /app && PYTHONPATH=/app python scripts/add_countries.py"
```

---

## Fase 5 — CI/CD Automático

Depois de configurados os GitHub Secrets:

```
git push origin main
       │
       ▼ (GitHub Actions)
  SSH para VPS
       │
  git pull + docker build + docker up
       │
  health check backend
       │
  seed idempotente
       │
  ✅ Deploy completo (~3-5 minutos)
```

Logs em: `GitHub → Actions → deploy.yml`

---

## Fase 6 — Verificação Pós-Deploy

```bash
# Saúde da API
curl https://teudominio.com/health

# Certificado SSL
curl -I https://teudominio.com

# Logs em tempo real
docker compose -f docker-compose.prod.yml logs -f

# Estado dos containers
docker compose -f docker-compose.prod.yml ps
```

### Checklist final
- [ ] `https://teudominio.com` abre (sem aviso SSL)
- [ ] Login/registo funciona
- [ ] Mapa mundial carrega com países coloridos
- [ ] Dashboard mostra guia ou botão de gerar
- [ ] Mapa local (LocalMap) geocodifica o código postal
- [ ] Notificações push funcionam (após configurar VAPID)

---

## Manutenção

### Actualizar a aplicação
```bash
# Automático: qualquer push para main faz deploy
git push origin main

# Manual (se necessário):
ssh root@<IP> "cd /opt/doomsday && git pull && docker compose -f docker-compose.prod.yml up -d --build"
```

### Backups da base de dados
```bash
# Dump manual
docker exec doomsday-postgres pg_dump -U doomsday doomsday > backup_$(date +%Y%m%d).sql

# Restaurar
docker exec -i doomsday-postgres psql -U doomsday doomsday < backup_20260313.sql
```

### Monitorização (opcional, free tier)
- [Better Uptime](https://betteruptime.com) — ping a `https://teudominio.com/health` a cada 3 min, alertas por email
- [Grafana Cloud](https://grafana.com) — métricas, logs (free tier generoso)

---

## Estimativa de Tempo

| Fase | Tempo estimado |
|------|---------------|
| 1. Criar servidor Hetzner | 5 min |
| 2. Configurar DNS | 5 min + propagação (até 24h) |
| 3. Gerar e guardar env vars | 15 min |
| 4. Bootstrap VPS + primeiro deploy | 20 min |
| 5. Configurar GitHub Secrets | 5 min |
| 6. Verificação final | 10 min |
| **Total** | **~1 hora** (excluindo propagação DNS) |

---

## Decisões Pendentes

- [ ] **Domínio:** qual usar? (`doomsdayprep.pt`, `prepara.pt`, outro?)
- [ ] **LLM:** na fase inicial usa fallback (guias pré-definidos). Quando quiseres guias IA reais, precisas de API key OpenAI/Anthropic ou servidor Ollama separado
- [ ] **Google OAuth:** queres login social? Precisas criar app em Google Cloud Console
- [ ] **News API:** queres feed real de notícias? Precisas de chave em [newsapi.org](https://newsapi.org) (free tier: 100 req/dia)
