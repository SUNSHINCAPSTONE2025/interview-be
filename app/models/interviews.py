# app/models/interview.py
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Integer,
    Date,
    DateTime,
    Text,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


class Interview(Base):

    __tablename__ = "content"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("user_profiles.id"), nullable=False, index=True)

    company = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False)

    role_category = Column(Integer, nullable=True)

    interview_date = Column(Date, nullable=False)
    jd_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    # 관계
    sessions = relationship(
        "InterviewSession",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    resumes = relationship(
        "Resume",
        back_populates="interview",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Resume(Base):

    __tablename__ = "resume"

    id = Column(BigInteger, primary_key=True, index=True)

    user_id = Column(UUID(as_uuid=True), ForeignKey("user_profiles.id"), nullable=False)
    content_id = Column(BigInteger, ForeignKey("content.id"), nullable=False)

    version = Column(Integer, nullable=False)

    question = Column(String(50), nullable=False)
    answer = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    interview = relationship("Interview", back_populates="resumes")
