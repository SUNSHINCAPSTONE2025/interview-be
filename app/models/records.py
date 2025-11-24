# app/models/records.py
from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON
from app.models.user import Base  # 같은 Base 공유

class PracticeRecord(Base):
    __tablename__ = "practice_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    interview_id = Column(Integer, ForeignKey("interviews.id"), nullable=False)

    company = Column(String(100), nullable=False)
    position = Column(String(100), nullable=False)

    category = Column(String(50), nullable=True)  # 예: "기술 면접"
    date = Column(Date, nullable=False)
    score = Column(Integer, nullable=True)

    # [{question, answer, feedback}, ...]
    questions = Column(JSON, nullable=True)
