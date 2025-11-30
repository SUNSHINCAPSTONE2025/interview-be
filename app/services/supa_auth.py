# app/services/supa_auth.py
from typing import Dict

from jose import JWTError, jwt
from app.config import settings

SUPABASE_JWT_SECRET = settings.supabase_jwt_secret

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
        # 🔍 우선은 *서명만* 검증 (aud/iss는 끔)
        claims = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={
                "verify_aud": False,
                "verify_iss": False,
            },
        )

    except JWTError as e:
        # 여기서 어떤 에러인지 로그에 남기기
        import logging

        logging.exception("JWT decode failed")
        raise ValueError("invalid token") from e

    user_id = claims.get("sub")
    email = claims.get("email")

    if not user_id:
        # sub가 없다 = 우리가 기대하는 Supabase access token 이 아님
        raise ValueError("invalid token: missing sub")

    return {
        "user_id": user_id,
        "email": email,
    }
