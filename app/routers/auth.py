# app/routers/auth.py
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.user_profile import UserProfile

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------- Schemas ----------
class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str | None = None
    display_name: str | None = None
    status: Literal["active", "blocked", "deleted"]
    created_at: datetime | None = None
    updated_at: datetime | None = None

class ProfileUpdateIn(BaseModel):
    display_name: str | None = Field(None, max_length=100)
    status: Literal["active", "blocked", "deleted"] | None = None

# ---------- Helpers ----------
def _guard_blocked(profile: UserProfile):
    if profile.status == "blocked":
        # 서비스 정책에 맞춰 메시지 조정 가능
        raise HTTPException(status_code=403, detail="account_blocked")

# ---------- Endpoints ----------
@router.get("/me", response_model=MeOut, response_model_exclude_none=True)
def me(user=Depends(get_current_user)):
    """
    현재 로그인한 사용자 정보 조회.
    - 인증: Supabase Access Token (Authorization: Bearer <token>)
    - 반환: auth.users.id(=id), email(토큰 클레임), user_profiles의 표시명/상태/타임스탬프
    """
    profile: UserProfile = user["profile"]
    _guard_blocked(profile)
    return MeOut(
        id=user["id"],
        email=user["email"],
        display_name=profile.display_name,
        status=profile.status,
        created_at=getattr(profile, "created_at", None),
        updated_at=getattr(profile, "updated_at", None),
    )

@router.patch("/profile", response_model=MeOut, response_model_exclude_none=True)
def update_profile(
    body: ProfileUpdateIn,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    내 프로필 수정 (표시이름/상태).
    - RLS로 본인 행만 수정 가능.
    - status는 'active' | 'blocked' | 'deleted' 만 허용.
    """
    profile: UserProfile = user["profile"]
    _guard_blocked(profile)

    if body.display_name is not None:
        profile.display_name = body.display_name.strip() or None
    if body.status is not None:
        profile.status = body.status

    db.add(profile)  # get_db()가 커밋/롤백 처리

    return MeOut(
        id=user["id"],
        email=user["email"],
        display_name=profile.display_name,
        status=profile.status,
        created_at=getattr(profile, "created_at", None),
        updated_at=getattr(profile, "updated_at", None),
    )

@router.post("/logout", status_code=204)
def logout():
    """
    서버 세션은 없음. 클라에서 supabase.auth.signOut() 호출.
    이 엔드포인트는 UX용으로 204만 반환.
    """
    return
