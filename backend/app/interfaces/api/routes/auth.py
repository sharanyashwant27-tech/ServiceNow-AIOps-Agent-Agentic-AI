from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dto.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.core.security import create_access_token, hash_password, verify_password
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import get_db
from app.interfaces.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserOut:
    existing = (await db.scalars(select(UserModel).where(UserModel.email == body.email))).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = UserModel(
        id=str(uuid4()),
        email=body.email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = (await db.scalars(select(UserModel).where(UserModel.email == body.email))).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.email, {"role": user.role, "name": user.full_name})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(user: UserModel = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role)
