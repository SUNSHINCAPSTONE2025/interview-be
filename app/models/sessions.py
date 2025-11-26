# app/models/sessions.py
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.db.base import Base

class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id = Column(BigInteger, primary_key=True, index=True)

    # dev 필드
    interview_id = Column(BigInteger, ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default="ongoing")  # ongoing|completed|draft|running|done|canceled
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # feat#6 필드 추가
    user_id = Column(BigInteger, index=True, nullable=True)
    content_id = Column(BigInteger, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    session_max = Column(Integer, default=1)

    # 관계
    interview = relationship("Interview", back_populates="sessions")