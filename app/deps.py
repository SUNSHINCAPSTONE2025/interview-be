# app/deps.py
from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.base import SessionLocal
from app.services.supabase_auth import verify_bearer
from app.models.user_profile import UserProfile

def get_db():
    # SQLAlchemy 세션 DI. commit / rollback은 여기서 처리
    db = SessionLocal()
    try:
        yield db; db.commit()
    except:
        db.rollback(); raise
    finally:
        db.close()

async def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """
    - Supabase Access Token(JWT)을 검증
    - 첫 접근이면 user_profiles(id=auth.users.id) 를 생성
    - 이후 라우터에서 user["id"], user["email"], user["profile"] 사용
    """
    try:
        claims = await verify_bearer(authorization)
        # claims: {"user_id": <uuid string>, "email": <str|None>}
    except Exception as e:
        # 세부 오류는 굳이 노출하지 않음
        raise HTTPException(status_code=401, detail="unauthorized") from e

    # upsert profile (없으면 생성)
    prof = db.get(UserProfile, claims["user_id"])
    if prof is None:
        prof = UserProfile(id=claims["user_id"], status="active")
        db.add(prof)
        db.flush()  # id는 이미 있으니 flush로 OK

    return {
        "id": claims["user_id"],          # = auth.users.id (uuid)
        "email": claims.get("email"),
        "profile": prof,                  # SQLAlchemy 객체
    }