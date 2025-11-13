# app/services/supabase_auth.py
from jose import jwt
import httpx, time, os

JWKS_URL = os.getenv("SUPABASE_JWKS_URL")  # https://<project>.supabase.co/auth/v1/keys
ISSUER   = os.getenv("SUPABASE_ISSUER")    # https://<project>.supabase.co/auth/v1
AUD      = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")

_cache, _ts = None, 0
async def _jwks():
    global _cache, _ts
    if not _cache or time.time() - _ts > 3600:
        async with httpx.AsyncClient(timeout=10) as c:
            _cache = (await c.get(JWKS_URL)).json()
        _ts = time.time()
    return _cache

async def verify_bearer(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise ValueError("missing_token")
    token = auth_header.split(" ", 1)[1]
    claims = jwt.decode(
        token, await _jwks(),
        audience=AUD, issuer=ISSUER, algorithms=["RS256"],
        options={"verify_at_hash": False}
    )
    return {"user_id": claims["sub"], "email": claims.get("email")}
