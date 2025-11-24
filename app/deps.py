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

# app/deps.py
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
