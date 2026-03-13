from typing import Optional, List
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    language: str = "pt"


class UserProfileUpdate(BaseModel):
    country_code: Optional[str] = None
    zip_code: Optional[str] = None
    household_size: Optional[int] = None
    housing_type: Optional[str] = None
    has_vehicle: Optional[bool] = None
    language: Optional[str] = None
    health_data_consent: Optional[bool] = None
    health_conditions: Optional[dict] = None
    preferences: Optional[dict] = None


class UserOut(BaseModel):
    id: str
    email: str
    auth_provider: str
    country_code: Optional[str]
    zip_code: Optional[str]
    household_size: Optional[int]
    housing_type: Optional[str]
    has_vehicle: Optional[bool]
    language: str
    health_data_consent: bool
    family_group_id: Optional[str]
    preferences: Optional[dict] = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
