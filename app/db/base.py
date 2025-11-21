# app/db/base.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Supabase에서 복사한 DB 연결 문자열을 .env에 넣어두고 씀
DATABASE_URL = settings.database_url

if not DATABASE_URL:
    # 개발할 때 env 빠뜨리면 바로 알 수 있게 로그
    raise RuntimeError("DATABASE_URL 환경변수가 설정되어 있지 않습니다.")

# SQLAlchemy 엔진 생성
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # 끊어진 커넥션 자동 감지
)

# 세션 팩토리 (FastAPI에서 DI로 쓰는 SessionLocal)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모든 모델이 공유할 베이스 클래스
Base = declarative_base()
