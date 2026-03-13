# Doomsday Prep Platform — Developer Guide

## Architecture

**Stack:** Next.js 15 (App Router) + FastAPI + PostgreSQL + Docker

```
doomsday/
├── backend/          FastAPI (Python 3.12)
│   ├── app/
│   │   ├── api/routes/       REST endpoints
│   │   ├── models/           SQLAlchemy ORM models
│   │   ├── services/
│   │   │   ├── content/      guide_service.py, poi_service.py
│   │   │   ├── llm/          LLM factory (Qwen/fallback)
│   │   │   └── notifications/push.py (pywebpush)
│   │   └── core/config.py    Settings (VAPID, DB, etc.)
│   └── scripts/
│       ├── generate_vapid.py     Generate VAPID key pair for web push
│       └── add_countries.py      Idempotent: insert missing country risk scores
├── frontend/         Next.js 15 (src/app router)
│   ├── src/
│   │   ├── app/              Pages (dashboard, profile, login, register)
│   │   ├── components/
│   │   │   ├── map/          WorldMap.tsx, LocalMap.tsx
│   │   │   ├── clock/        DoomsdayClock.tsx, NavClock.tsx
│   │   │   ├── guide/        CategoryPreview.tsx, VaultIcons.tsx
│   │   │   └── ui/           PushToggle.tsx, AppInit.tsx
│   │   └── lib/
│   │       ├── api.ts        API client + types
│   │       ├── categories.ts Category metadata + colors
│   │       ├── i18n.ts       Zustand i18n (PT/EN)
│   │       ├── push.ts       Web Push / Service Worker helpers
│   │       └── store.ts      Zustand (auth, clock, world map)
│   └── public/
│       ├── sw.js             Service Worker (push notifications)
│       └── locales/          pt.json, en.json
└── data/clusters/            Server-side guide cluster cache (JSON)
```

## Running Locally

```bash
docker compose up          # starts backend (8000) + frontend (3000) + postgres
```

Frontend runs in **dev mode** inside Docker with hot-reload via volume mounts.
`npm run build` on host fails (Node 25 incompatibility) — always build inside container.

## Key Patterns

### Guide Generation
- `guide_service.py`: LLM → FALLBACK_GUIDE → cluster cache → DB (Guide + GuideVersion)
- **Critical**: Always `await db.flush()` after `db.add(version)` BEFORE setting `guide.current_version_id`
- `GuideVersion.rollback_available`: set explicitly (False for v1, `next_version > 1` for later)
- Cluster cache key = `sha256(country|zip|household_size|housing_type|language)[:16]`

### POI Map (LocalMap)
- Nominatim geocoding: strip zip suffix (`4200-369` → `4200`), use `postalcode+countrycodes` params
- Overpass API: 3-retry with exponential backoff for 504 timeouts
- Frontend uses `postalcode=PREFIX&countrycodes=cc` (NOT `country=PT` which returns Italy)

### Leaflet (WorldMap)
- `filterZoomEvent`: only zoom on `Ctrl+Scroll` to avoid capturing page scroll
- StrictMode double-mount: check `(mapRef.current as any)._leaflet_id` before re-initializing

### Guide Timeline View
- Priority → timeline: `1 → 7d`, `2 → 30d`, `3 → 180d`, `4+/undefined → 360d`
- `TIMELINES` const in `dashboard/page.tsx`; `CATEGORY_META` in `categories.ts` has `color` per category

### Push Notifications
1. Generate VAPID keys: `python backend/scripts/generate_vapid.py`
2. Add to `.env`: `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_EMAIL`
3. Add to frontend `.env.local`: `NEXT_PUBLIC_VAPID_PUBLIC_KEY`

### i18n
- `src/lib/i18n.ts`: Zustand store, locale persisted to localStorage
- Locale files: `public/locales/pt.json`, `public/locales/en.json`
- `AppInit.tsx` in layout: loads locale on mount

### Country Risk Data
- **41 countries** seeded (10 original + 31 added via `scripts/add_countries.py`)
- Risk scale: `green ≥83s · yellow 70-82s · orange 63-69s · red ≤62s`
- To add more countries to a running instance: `docker exec doomsday-backend sh -c "cd /app && PYTHONPATH=/app python scripts/add_countries.py"`
- For fresh installs: `seed_data.py` now includes all 41 countries
- NUM2ISO map in `WorldMap.tsx` must include numeric TopoJSON IDs for new countries to appear coloured

### Category Cards (Homepage)
- `CategoryPreview.tsx` is a client component (`"use client"`)
- On click: modal shows category description + item checklist (from localStorage) + CTA to guide
- Auth state from `useAuthStore()` determines which modal variant to show (guest / no guide / with guide)
- Deep-link: CTA goes to `/dashboard?cat=<id>` → dashboard reads `useSearchParams`, opens accordion, scrolls to category

## Deployment (Production)

### Architecture
```
Internet → Nginx (80/443, SSL) → Frontend :3000 (Next.js standalone)
                               → Backend  :8000 (FastAPI)
                      PostgreSQL :5432 (internal)
                      Redis      :6379 (internal)
```

### Option A — VPS (Hetzner/DO, recommended for EU/GDPR)
1. Spin up Ubuntu 22.04, min 2GB RAM (Hetzner CX22 €3.79/mo)
2. `bash scripts/setup-vps.sh yourdomain.com your@email.com`
3. Copy `.env` to `/opt/doomsday/.env` (see `.env.example`)
4. `docker compose -f docker-compose.prod.yml up -d --build`

### Option B — Vercel (frontend) + Railway (backend)
- Frontend: connect GitHub repo to Vercel, set `NEXT_PUBLIC_API_URL` env var
- Backend: connect GitHub repo to Railway, add all backend env vars
- DB: Railway PostgreSQL add-on
- Redis: Railway Redis add-on or Upstash free tier

### CI/CD (GitHub Actions)
Required secrets in GitHub → Settings → Secrets:
| Secret | Value |
|--------|-------|
| `VPS_HOST` | Server IP or hostname |
| `VPS_USER` | SSH user (usually `root`) |
| `VPS_SSH_KEY` | Private SSH key (ed25519) |
| `PROD_ENV` | Full contents of production `.env` file |

Push to `main` → auto-deploys to VPS (pulls code, rebuilds, seeds DB).

### Required env vars for production (beyond dev defaults)
```
SECRET_KEY=<random 64-char string>
POSTGRES_PASSWORD=<strong password>
CORS_ORIGINS=["https://yourdomain.com"]
NEXT_PUBLIC_API_URL=https://yourdomain.com
VAPID_PRIVATE_KEY=<from generate_vapid.py>
VAPID_PUBLIC_KEY=<from generate_vapid.py>
VAPID_CLAIMS_EMAIL=your@email.com
NEXT_PUBLIC_VAPID_PUBLIC_KEY=<same as VAPID_PUBLIC_KEY>
```

### SSL Certificates
- Auto-managed by `setup-vps.sh` via Let's Encrypt / certbot
- Cron auto-renews every day at 03:00 and reloads nginx
- Certs stored in `nginx/certs/` (gitignored)

## SQLAlchemy Async Rules
- **Never** access relationship attributes (`.versions`, `.user`) without explicit loading
- Use `select(...).where(...)` queries instead of lazy-loaded attributes
- Use `selectinload()` if you need relationships
