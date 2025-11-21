from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
# ▶ user.py에서 선언한 Base를 재사용(같은 메타데이터로 테이블 생성)
from app.db.base import Base

class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    # 필요 시 사용자별 소유를 구분하려면 주석 해제
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    company = Column(String(100), nullable=False)
    position = Column(String(100), nullable=False)

    # 면접 날짜(없을 수 있음)
    interview_date = Column(Date, nullable=True)

    # 전체 연습 세션 수와 완료 수
    total_sessions = Column(Integer, default=10, nullable=False)
    completed_sessions = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    # 관계(면접 연습 세션)
    sessions = relationship("InterviewSession", back_populates="interview", cascade="all, delete-orphan")
