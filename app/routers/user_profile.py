# app/routers/user_profile.py

from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session
from uuid import UUID

from app.deps import get_current_user, get_db
from app.models.user_profile import UserProfile

router = APIRouter(prefix="/api/me", tags=["me"])

# ---- Pydantic 스키마 ----

class UserProfileOut(BaseModel):
    id: UUID
    display_name: Optional[str] = None
    status: str
    profile_meta: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    status: Optional[str] = None      # 필요하면 Literal로 제한 가능
    profile_meta: Optional[Dict[str, Any]] = None


# ---- 내 프로필 조회 ----

@router.get("/profile", response_model=UserProfileOut)
async def get_my_profile(
    current = Depends(get_current_user),
):
    prof: UserProfile = current["profile"]
    return prof


# ---- 내 프로필 수정 (회원가입 후 display_name 설정 등) ----

@router.put("/profile", response_model=UserProfileOut)
async def update_my_profile(
    payload: UserProfileUpdate,
    current = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prof: UserProfile = current["profile"]

    if payload.display_name is not None:
        prof.display_name = payload.display_name

    if payload.status is not None:
        prof.status = payload.status

    if payload.profile_meta is not None:
        prof.profile_meta = payload.profile_meta

    db.add(prof)  # get_db가 함수 끝난 뒤 commit 해줌
    return prof