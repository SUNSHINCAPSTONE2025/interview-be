from sqlalchemy import Column, BigInteger, Float, Text
from app.db.base import Base


class FeedbackSummary(Base):

    __tablename__ = "feedback_summary"

    session_id = Column(BigInteger, primary_key=True, index=True)

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