# app/models/user_profile.py
# supabase auth.users를 보조하는 프로필 테이블 모델
from sqlalchemy import Column, String, DateTime, text, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True)  # = auth.users.id (uuid)
    display_name = Column(String(100))
    status = Column(
        Enum("active", "blocked", "deleted", name="user_status", native_enum=False),
        nullable=False,
        server_default=text("'active'")
    )
    profile_meta = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))