# app/models/basic_question.py
from sqlalchemy import Column, BigInteger, String, Text, DateTime, func
from app.db.base import Base

class BasicQuestion(Base):
    __tablename__ = "basic_question"

    id = Column(BigInteger, primary_key=True, index=True)
    label = Column(String(20), nullable=False) # job|soft
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
