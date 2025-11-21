# app/db/models.py
# DB 모델: sessions, session_question, attempts, media_asset, feedback_summary
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Float, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.session import Base

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)

class Content(Base):
    __tablename__ = "content"
    id = Column(BigInteger, primary_key=True)

class SessionQuestion(Base):
    __tablename__ = "session_question"
    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, index=True)
    question_type = Column(String(20))
    question_id = Column(BigInteger)
    order_no = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class InterviewSession(Base):
    __tablename__ = "sessions"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, index=True)
    content_id = Column(BigInteger, index=True)
    status = Column(String(20), default="draft")  # draft|running|done|canceled
    started_at = Column(DateTime)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)
    session_max = Column(Integer, default=1)

class Attempt(Base):
    __tablename__ = "attempts"
    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, index=True)
    session_question_id = Column(BigInteger, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    duration_sec = Column(Float, nullable=True)
    status = Column(String(20), nullable=True)  # ok|aborted|pending
    stt_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class MediaAsset(Base):
    __tablename__ = "media_asset"
    id = Column(BigInteger, primary_key=True)
    session_id = Column(BigInteger, index=True, nullable=False)
    attempt_id = Column(BigInteger, index=True, nullable=True)
    session_question_id = Column(BigInteger, nullable=True)
    kind = Column(Integer, nullable=False)  # video=1,image=2,audio=3
    storage_url = Column(Text, nullable=False)  # 외부 스토리지 URL 또는 로컬 파일경로
    sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

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

    created_at = Column(DateTime, default=datetime.utcnow)
