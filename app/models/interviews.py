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
from sqlalchemy.orm import relationship
from app.models.user_profile import Base


class Interview(Base):

    __tablename__ = "content"

    id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(String(64), nullable=False)

    company = Column(String, nullable=False)
    role = Column(String, nullable=False)

    role_category = Column(Integer, nullable=False, default=0)

    interview_date = Column(Date, nullable=True)
    jd_text = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

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

    user_id = Column(String(64), nullable=False)
    content_id = Column(
        BigInteger, ForeignKey("content.id"), nullable=False
    )

    version = Column(Integer, nullable=False, default=1)

    question = Column(String, nullable=False)
    answer = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    interview = relationship("Interview", back_populates="resumes")