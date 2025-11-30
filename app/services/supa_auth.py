# app/services/supa_auth.py
import os
from typing import Dict
from jose import jwt, JWTError
from app.config import settings

SUPABASE_JWT_SECRET = settings.supabase_jwt_secret
SUPABASE_ISSUER = settings.supabase_issuer
SUPABASE_JWT_AUDIENCE = settings.supabase_jwt_audience

if not SUPABASE_JWT_SECRET:
    raise RuntimeError("SUPABASE_JWT_SECRET 환경변수가 설정되어 있지 않습니다.")


async def verify_bearer(authorization: str | None) -> Dict[str, str | None]:
    if not authorization:
        raise ValueError("missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ValueError("invalid Authorization header")

    token = parts[1].strip()
    if not token:
        raise ValueError("invalid Authorization header")

    try:
        # 👉 우선은 최소 설정만: secret + algorithm
        claims = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={
                "verify_aud": False,   # aud 검증 끔
                "verify_iss": False,   # iss 검증 끔
            },
        )

    except JWTError as e:
        # 디버깅용으로 로그 남겨보는 것도 좋음
        print("JWT decode error:", repr(e))
        raise ValueError("invalid token") from e

    # sub / email 없는 토큰(anon key 등)을 잘못 넣었을 때 대비
    user_id = claims.get("sub")
    email = claims.get("email")

    if not user_id:
        raise ValueError("invalid token: missing sub")

    return {
        "user_id": user_id,
        "email": email,
    }