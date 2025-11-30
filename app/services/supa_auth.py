# app/services/supa_auth.py
from typing import Dict

from jose import JWTError, jwt

from app.config import settings

SUPABASE_JWT_SECRET = settings.supabase_jwt_secret

if not SUPABASE_JWT_SECRET:
    raise RuntimeError("SUPABASE_JWT_SECRET 환경변수가 설정되어 있지 않습니다.")


async def verify_bearer(authorization: str | None) -> Dict[str, str | None]:
    """
    Authorization: Bearer <access_token> 헤더에서 토큰을 꺼내서
    Supabase JWT secret(HS256)으로만 검증하고,
    sub / email을 꺼낸다.
    (aud / iss 검증은 일단 끈 상태)
    """
    if not authorization:
        raise ValueError("missing Authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ValueError("invalid Authorization header")

    token = parts[1].strip()
    if not token:
        raise ValueError("invalid Authorization header")

    try:
        # ✨ 디버깅을 위해 aud/iss 검증은 끄고, 서명만 확인
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
        # Render 로그에서 실제 에러 타입을 보기 위해 출력
        import logging

        logging.exception("JWT decode failed: %r", e)
        raise ValueError("invalid token") from e

    user_id = claims.get("sub")
    email = claims.get("email")

    if not user_id:
        # sub 없으면 이 토큰은 우리가 기대한 형태가 아님 (anon key 같은 것)
        raise ValueError("invalid token: missing sub")

    return {
        "user_id": user_id,
        "email": email,
    }
