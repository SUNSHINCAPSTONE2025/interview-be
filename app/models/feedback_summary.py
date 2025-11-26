from sqlalchemy import Column, BigInteger, Float, Text, DateTime, func
from sqlalchemy.types import JSON
from app.db.base import Base

class FeedbackSummary(Base):
    __tablename__ = "feedback_summary"
    session_id = Column(BigInteger, primary_key=True, index=True)  # 1:1 with sessions.id
    overall = Column(Float, nullable=True)
    overall_face = Column(Float, nullable=True)
    overall_voice = Column(Float, nullable=True)
    overall_pose = Column(Float, nullable=True)

    gaze = Column(Float, nullable=True)
    eye_blink = Column(Float, nullable=True)
    mouth = Column(Float, nullable=True)

    tremor = Column(Float, nullable=True)
    blank = Column(Float, nullable=True)
    tone = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)

    shoulder = Column(Float, nullable=True)
    head = Column(Float, nullable=True)
    hand = Column(Float, nullable=True)

    speech = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)

    # 추가: 자세 문제 구간을 JSON으로 저장
    problem_sections = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)