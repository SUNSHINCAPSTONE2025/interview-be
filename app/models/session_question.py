# app/models/session_question.py
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, ForeignKey, Index, func
from app.db.base import Base

class SessionQuestion(Base):
    __tablename__ = "session_question"

    id = Column(BigInteger, primary_key=True, index=True)
    session_id = Column(BigInteger, ForeignKey("sessions.id"), nullable=False, index=True)
    question_type = Column(String(20), nullable=False)  # BASIC|GENERATED
    question_id = Column(BigInteger, nullable=False)
    order_no = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_session_question_session_id_order_no', 'session_id', 'order_no'),
        Index('ix_session_question_type_id', 'question_type', 'question_id'),
    )