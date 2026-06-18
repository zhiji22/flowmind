import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from jose import jwt
from passlib.context import CryptContext

from app.config import settings
from app.services.token_blacklist import is_revoked

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt 只对前 72 字节敏感；bcrypt>=4.0 不再静默截断长输入会直接报错。
# 在入口处统一按 UTF-8 字节裁剪到 72，保证 hash / verify 使用相同输入。
_BCRYPT_MAX_BYTES = 72


def _truncate_for_bcrypt(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


class TokenClaims(TypedDict):
    sub: str
    jti: str
    exp: int


def hash_password(password: str) -> str:
    return pwd_context.hash(_truncate_for_bcrypt(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(_truncate_for_bcrypt(plain_password), hashed_password)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "jti": uuid.uuid4().hex,  # token 唯一 id，用于黑名单
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenClaims | None:
    """解析并校验 token；返回完整 claims 或 None。

    检查：签名 / 过期 / 黑名单。
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except Exception:
        return None

    sub = payload.get("sub")
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not sub or not jti or not exp:
        return None

    if is_revoked(jti):
        return None

    return TokenClaims(sub=sub, jti=jti, exp=int(exp))
