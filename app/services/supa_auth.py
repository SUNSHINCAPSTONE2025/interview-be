# app/services/supa_auth.py
from typing import Dict
from jose import JWTError, jwt
from app.config import settings
import hashlib, logging

SUPABASE_JWT_SECRET = settings.supabase_jwt_secret

if not SUPABASE_JWT_SECRET:
    raise RuntimeError("SUPABASE_JWT_SECRET 환경변수가 설정되어 있지 않습니다.")

secret_hash = hashlib.sha256(SUPABASE_JWT_SECRET.encode()).hexdigest()
logging.warning("JWT secret sha256 (first 12) = %s", secret_hash[:12])

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
        import logging
        logging.exception("JWT decode failed")  # 🔍 여기
        raise ValueError("invalid token") from e

    user_id = claims.get("sub")
    email = claims.get("email")

    if not user_id:
        raise ValueError("invalid token: missing sub")

    return {
        "user_id": user_id,
        "email": email,
    }
