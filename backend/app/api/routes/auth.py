"""Authentication routes: email/password + Google OAuth"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_password, hash_password, create_access_token
from app.models.user import User
from app.schemas.user import UserCreate, TokenResponse, UserOut

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        hashed_password=hash_password(payload.password),
        auth_provider="email_password",
        language=payload.language,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/google")
async def google_login():
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")
    from authlib.integrations.httpx_client import AsyncOAuth2Client
    client = AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri="http://localhost:8000/api/auth/google/callback",
        scope="openid email profile",
    )
    uri, _ = client.create_authorization_url("https://accounts.google.com/o/oauth2/v2/auth")
    return RedirectResponse(uri)


@router.get("/google/callback")
async def google_callback(code: str, db: AsyncSession = Depends(get_db)):
    from authlib.integrations.httpx_client import AsyncOAuth2Client
    client = AsyncOAuth2Client(
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        redirect_uri="http://localhost:8000/api/auth/google/callback",
    )
    await client.fetch_token("https://oauth2.googleapis.com/token", code=code)
    userinfo_resp = await client.get("https://www.googleapis.com/oauth2/v3/userinfo")
    google_data = userinfo_resp.json()

    google_id = google_data["sub"]
    email = google_data["email"]

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()
    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.google_id = google_id
            user.auth_provider = "google_oauth"
        else:
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                google_id=google_id,
                auth_provider="google_oauth",
            )
            db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_access_token({"sub": user.id})
    return RedirectResponse(f"http://localhost:3000/auth/callback?token={token}")
