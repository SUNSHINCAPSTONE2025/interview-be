# app/models/attempt.py
from sqlalchemy import Column, BigInteger, Float, String, Text, DateTime, func
from app.db.base import Base

class Attempt(Base):
    __tablename__ = "attempts"

    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, index=True, nullable=False)
    session_question_id = Column(BigInteger, index=True, nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Float, nullable=True)

    status = Column(String(20), nullable=True)  # ok | aborted | pending
    stt_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)