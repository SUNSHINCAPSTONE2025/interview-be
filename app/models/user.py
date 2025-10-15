# app/models/user.py
# User 테이블(SQLAlchemy) 스키마 정의
# 필드, 이메일 인증 토큰, 생성일 등 모델 선언
from sqlalchemy import Boolean, Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base
Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email_verified = Column(Boolean, default=False)
    email_verify_token = Column(String(255), nullable=True)  # 인증/재설정 공용 토큰
    created_at = Column(DateTime, server_default=func.now())
