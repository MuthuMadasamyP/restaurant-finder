from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str


class FeedbackCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    feedback: str = Field(..., min_length=2, max_length=3000)


class StarHotelCreate(BaseModel):
    hotel_name: str = Field(..., min_length=1, max_length=255)
    area: str = Field(..., min_length=1, max_length=160)


class FavouriteRestaurantCreate(BaseModel):
    restaurant_name: str = Field(..., min_length=1, max_length=255)
    search_area: str = Field(..., min_length=1, max_length=255)
    rating: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=500)


class SettingsUpdate(BaseModel):
    daily_search_limit: int = Field(..., ge=1, le=100)
    special_event_limit: int = Field(..., ge=1, le=100)
    event_enabled: bool
    active_user_days: int = Field(default=30, ge=1, le=365)


class SettingsResponse(SettingsUpdate):
    effective_limit: int


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    status: str
    created_at: datetime
    last_login_at: datetime | None


class UserStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|inactive|blocked)$")
