from sqlalchemy import Column, BigInteger, Numeric, Text, ForeignKey
from app.db.base import Base

class FeedbackSummary(Base):
    __tablename__ = "feedback_summary"

    session_id = Column(BigInteger, ForeignKey("sessions.id"), primary_key=True, index=True)  # 1:1 with sessions.id

    overall = Column(Numeric(5, 2), nullable=True)
    overall_face = Column(Numeric(5, 2), nullable=True)
    overall_voice = Column(Numeric(5, 2), nullable=True)
    overall_pose = Column(Numeric(5, 2), nullable=True)

    gaze = Column(Numeric(5, 2), nullable=True)
    eye_blink = Column(Numeric(5, 2), nullable=True)
    mouth = Column(Numeric(5, 2), nullable=True)

    tremor = Column(Numeric(5, 2), nullable=True)
    blank = Column(Numeric(5, 2), nullable=True)
    tone = Column(Numeric(5, 2), nullable=True)
    speed = Column(Numeric(5, 2), nullable=True)

    shoulder = Column(Numeric(5, 2), nullable=True)
    head = Column(Numeric(5, 2), nullable=True)
    hand = Column(Numeric(5, 2), nullable=True)

    speech = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)