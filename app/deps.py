# app/deps.py
from fastapi import Header, HTTPException, Depends
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
    db: Session = Depends(get_db),
):
    try:
        claims = await verify_bearer(authorization)
    except Exception as e:
        print("verify_bearer failed >>>", repr(e))
        raise HTTPException(status_code=401, detail="unauthorized")

    prof = db.get(UserProfile, claims["user_id"])
    if prof is None:
        prof = UserProfile(id=claims["user_id"], status="active")
        db.add(prof)
        db.flush()

    return {
        "id": claims["user_id"],
        "email": claims.get("email"),
        "profile": prof,
    }

# ----------------------------
# 추가 의존성: feat#6 필요 기능
# ----------------------------
# 예시: pose 모델
from app.services.pose_model import PoseModel
def get_pose_model():
    return PoseModel()

# 예시: storage service
from app.services.storage_service import StorageService
def get_storage_service():
    return StorageService()