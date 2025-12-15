# app/models/generated_question.py
from sqlalchemy import Column, BigInteger, String, Boolean, Text, DateTime, ForeignKey, Index, func
from app.db.base import Base

class GeneratedQuestion(Base):
    __tablename__ = "generated_question"

    id = Column(BigInteger, primary_key=True, index=True)
    content_id = Column(BigInteger, ForeignKey("content.id"), nullable=False)
    type = Column(String(20), nullable=False)  # job|soft
    is_used = Column(Boolean, nullable=False, default=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_generated_question_content_id_created_at', 'content_id', 'created_at'),
    )
