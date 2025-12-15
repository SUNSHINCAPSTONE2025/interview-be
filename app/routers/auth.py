# 실제 API 라우터
# /api/auth의 회원가입/로그인/이메일 인증/비번 재설정/토큰 재발급
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.deps import get_db
from app.models.user import User
from app.routers.services import auth as svc
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------- utils ----------
def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()

def bearer_token(auth_header: Optional[str]) -> str:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"message": "unauthorized"})
    return auth_header.split()[1]

# ---------- endpoints ----------
@router.post("/signup", status_code=201)
def signup(payload: svc.SignupIn, db: Session = Depends(get_db)):
    if get_user_by_email(db, payload.email):
        raise HTTPException(status_code=409, detail={"message": "email_already_in_use"})
    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=svc.hash_password(payload.password),
        email_verified=False,
        email_verify_token=str(__import__("uuid").uuid4()),
    )
    db.add(user); db.commit(); db.refresh(user)
    svc.send_verification_email(user.email, user.email_verify_token)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "email_verified": user.email_verified,
    }

@router.post("/login")
def login(payload: svc.LoginIn, db: Session = Depends(get_db), x_forwarded_for: Optional[str] = Header(None)):
    key = f"{x_forwarded_for or 'local'}:{payload.email}"
    if svc.too_many_attempts(key, settings.RATE_LIMIT_ATTEMPTS, settings.RATE_LIMIT_WINDOW_SEC):
        raise HTTPException(status_code=429, detail={"message":"rate_limited","detail":"Too many login attempts. Try again later."})

    user = get_user_by_email(db, payload.email)
    if not user or not svc.verify_password(payload.password, user.password_hash):
        svc.record_attempt(key)
        raise HTTPException(status_code=401, detail={"message":"invalid_credentials","detail":"email or password is incorrect"})
    if not user.email_verified:
        raise HTTPException(status_code=403, detail={"message":"email_not_verified","detail":"Please verify your email before logging in"})

    return {
        "message": "login_success",
        "access_token": svc.create_access_token(str(user.id)),
        "refresh_token": svc.create_refresh_token(str(user.id)),
        "user": {"id": f"u{user.id}", "name": user.name, "email": user.email, "email_verified": user.email_verified},
    }

@router.post("/verify-email/send")
def verify_email_send(payload: svc.EmailIn, db: Session = Depends(get_db)):
    user = get_user_by_email(db, payload.email)
    # 보안상 존재여부는 노출하지 않음
    if user:
        import uuid
        user.email_verify_token = str(uuid.uuid4())
        db.add(user); db.commit()
        svc.send_verification_email(user.email, user.email_verify_token)
    return {"message": "verification_email_sent"}

@router.post("/verify-email/confirm")
def verify_email_confirm(payload: svc.TokenIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email_verify_token == payload.token).first()
    if not user:
        raise HTTPException(status_code=400, detail={"message": "invalid_or_expired_token"})
    user.email_verified = True
    user.email_verify_token = None
    db.add(user); db.commit()
    return {"message": "email_verified_successfully"}

@router.post("/password/forgot")
def password_forgot(payload: svc.EmailIn, db: Session = Depends(get_db)):
    user = get_user_by_email(db, payload.email)
    if user:
        import uuid
        user.email_verify_token = str(uuid.uuid4())  # reset 토큰으로 사용
        db.add(user); db.commit()
        svc.send_password_reset_email(user.email, user.email_verify_token)
    return {"message": "password_reset_email_sent"}

@router.post("/password/reset")
def password_reset(payload: svc.PasswordResetIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email_verify_token == payload.token).first()
    if not user:
        raise HTTPException(status_code=400, detail={"message": "invalid_or_expired_token"})
    user.password_hash = svc.hash_password(payload.new_password)
    user.email_verify_token = None
    db.add(user); db.commit()
    return {"message": "password_reset_success"}

@router.post("/token/refresh")
def token_refresh(payload: svc.TokenRefreshIn):
    try:
        data = svc.decode_token(payload.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail={"message":"invalid_refresh_token"})
    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail={"message":"invalid_refresh_token"})
    new_access = svc.create_access_token(data["sub"])
    return {"message": "token_refreshed", "access_token": new_access}

@router.get("/me")
def me(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    token = bearer_token(authorization)
    try:
        data = svc.decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail={"message":"unauthorized"})
    if data.get("type") != "access":
        raise HTTPException(status_code=401, detail={"message":"unauthorized"})
    user = db.query(User).get(int(data["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail={"message":"unauthorized"})
    return {"id": user.id, "name": user.name, "email": user.email, "email_verified": user.email_verified}
