# app/models/session_question.py
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, func
from app.db.base import Base

class SessionQuestion(Base):
    __tablename__ = "session_question"

    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, index=True)
    question_type = Column(String(20))
    question_id = Column(BigInteger)
    order_no = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)