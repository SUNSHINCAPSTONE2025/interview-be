# app/models/sessions.py
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base

class InterviewSession(Base):
    __tablename__ = "sessions"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user_profiles.id"), nullable=False, index=True)
    content_id = Column(BigInteger, ForeignKey("content.id"), nullable=False)
    status = Column(String(20), nullable=False)  # draft|running|done|canceled
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    session_max = Column(Integer, nullable=False)

    __table_args__ = (
        Index('ix_sessions_user_id_started_at', 'user_id', 'started_at'),
    )

    # 관계
    interview = relationship("Interview", back_populates="sessions")