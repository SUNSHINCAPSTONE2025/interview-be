# app/api_deps.py
# get_db, get_current_user - 프로젝트에 이미 deps.py가 있으면 그걸 사용하세요.
from fastapi import Depends, HTTPException, Header
from app.db.session import SessionLocal
from sqlalchemy.orm import Session

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 간단한 토큰 기반 stub. 실제 프로젝트의 get_current_user (supabase/jwt) 로 대체하세요.
async def get_current_user(authorization: str | None = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="unauthorized")
    # 이 자리에 supabase/jwt 검증 로직을 연결하세요.
    # 예시 반환값:
    return {"id": 1, "email": "user@example.com"}
