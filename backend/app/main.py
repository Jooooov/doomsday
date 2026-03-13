"""
Doomsday Platform — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import init_db
from app.api.routes import auth, users, clock, guides, groups, map as map_router, notifications


limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Start background schedulers
    from app.services.clock.scheduler import start_clock_scheduler
    await start_clock_scheduler()
    yield
    # Cleanup


app = FastAPI(
    title="Doomsday Platform API",
    description="WW3 Preparedness Platform — Regional Doomsday Clock + Personalized Guides",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(clock.router, prefix="/api/clock", tags=["clock"])
app.include_router(guides.router, prefix="/api/guides", tags=["guides"])
app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
app.include_router(map_router.router, prefix="/api/map", tags=["map"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "doomsday-api"}
