# app/deps.py
from fastapi import Header, HTTPException
from sqlalchemy.orm import Session
from app.db.base import SessionLocal
from app.services.supa_auth import verify_bearer
from app.models.user_profile import UserProfile

# ----------------------------
# DB 세션
# ----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()  # commit 포함
    except:
        db.rollback()
        raise
    finally:
        db.close()

# ----------------------------
# 현재 사용자 가져오기
# ----------------------------
async def get_current_user(
    authorization: str | None = Header(None),
):
    """
    인증은 항상 짧은 DB 세션으로 처리해 커넥션 점유 시간을 최소화한다.
    """
    try:
        claims = await verify_bearer(authorization)
    except Exception as e:
        print("verify_bearer failed >>>", repr(e))
        raise HTTPException(status_code=401, detail="unauthorized")

    with SessionLocal() as db:
        prof = db.get(UserProfile, claims["user_id"])
        if prof is None:
            prof = UserProfile(id=claims["user_id"], status="active")
            db.add(prof)
            db.commit()
            db.refresh(prof)

    return {
        "id": claims["user_id"],
        "email": claims.get("email"),
        "profile": prof,
    }
