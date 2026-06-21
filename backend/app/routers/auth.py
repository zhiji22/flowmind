from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.services.token_blacklist import revoke

router = APIRouter()
security = HTTPBearer()


# 获取当前登录用户
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    claims = await decode_access_token(credentials.credentials)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的 token",
        )

    result = await db.execute(select(User).where(User.id == claims["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")

    return user


# 注册
@router.post("/register", response_model=TokenResponse)
@limiter.limit("3/hour")
async def register(request: Request, req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


# 登录
@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


# DEV 专用：直接重置已存在用户的密码（生产环境禁用）
@router.post("/reset-password")
@limiter.limit("3/hour")
async def reset_password(
    request: Request, req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
):
    # Fail-closed：仅 development/test 环境启用；任何其他值（含 production、
    # staging、未设置、拼写错误、大小写变体）一律 404，避免误开放账号接管接口。
    if settings.APP_ENV not in ("development", "test"):
        raise HTTPException(status_code=404, detail="Not Found")

    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.password_hash = hash_password(req.new_password)
    await db.commit()
    return {"message": "密码已重置"}


# 登出：把当前 token 加入黑名单（直到原本的 exp）
@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    claims = await decode_access_token(credentials.credentials)
    if claims:
        await revoke(claims["jti"], float(claims["exp"]))
    return {"message": "已登出"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
