# app/models/attempt.py
from sqlalchemy import Column, BigInteger, Numeric, String, Text, DateTime, ForeignKey, Index, func
from app.db.base import Base

class Attempt(Base):
    __tablename__ = "attempts"

    id = Column(BigInteger, primary_key=True, index=True)
    session_id = Column(BigInteger, ForeignKey("sessions.id"), nullable=False, index=True)
    session_question_id = Column(BigInteger, ForeignKey("session_question.id"), nullable=False)

    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Numeric(8, 2), nullable=True)

    status = Column(String(20), nullable=True)  # ok|aborted
    stt_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_attempts_session_id_question_id', 'session_id', 'session_question_id'),
        Index('ix_attempts_session_id_started_at', 'session_id', 'started_at'),
    )