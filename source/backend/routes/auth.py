from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.admin_data import Admin, User
from models.admin_schemas import LoginRequest, SignupRequest, TokenResponse
from services.auth import create_access_token, hash_password, verify_password

router = APIRouter()


@router.post("/auth/signup", response_model=TokenResponse)
def signup(request: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(User).filter(User.email == request.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    user = User(
        name=request.name.strip(),
        email=request.email.lower(),
        password_hash=hash_password(request.password),
        status="active",
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.email, role="user", user_id=user.id)
    return TokenResponse(access_token=token, role="user", name=user.name)


@router.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not request.email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Email is required")

    user = db.query(User).filter(User.email == request.email.lower()).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token(subject=user.email, role="user", user_id=user.id)
    return TokenResponse(access_token=token, role="user", name=user.name)


@router.post("/admin/login", response_model=TokenResponse)
def admin_login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not request.username:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username is required")

    admin = db.query(Admin).filter(Admin.username == request.username).first()
    if not admin or not verify_password(request.password, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials")

    token = create_access_token(subject=admin.username, role="admin", user_id=admin.id)
    return TokenResponse(access_token=token, role="admin", name=admin.username)
