# app/services/supabase_auth.py
import os
from typing import Dict

from jose import jwt, JWTError

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPABASE_ISSUER = os.getenv("SUPABASE_ISSUER")
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")

if not SUPABASE_JWT_SECRET:
    raise RuntimeError("SUPABASE_JWT_SECRET 환경변수가 설정되어 있지 않습니다.")


async def verify_bearer(authorization: str | None) -> Dict[str, str | None]:
    """
    - Authorization: Bearer <access_token> 헤더에서 토큰을 꺼내서
    - Supabase JWT secret(HS256)으로 검증하고
    - 기본적인 클레임(sub, email)을 반환한다.
    """
    if not authorization:
        raise ValueError("missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ValueError("invalid Authorization header")

    token = parts[1]

    try:
        claims = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],                 # 🔥 Supabase access token 의 alg
            audience=SUPABASE_JWT_AUDIENCE,      # "authenticated"
            issuer=SUPABASE_ISSUER,              # "https://.../auth/v1"
        )
    except JWTError as e:
        # get_current_user 쪽에서 401로 바꿔서 응답
        raise ValueError("invalid token") from e

    return {
        "user_id": claims["sub"],
        "email": claims.get("email"),
    }
