# app/db/session.py
# SQLAlchemy 기본 세팅. DB URL은 .env의 DATABASE_URL을 사용.

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings  # Settings() 인스턴스

# Supabase Postgres 연결용 URL (예: postgresql+psycopg2://...)
DATABASE_URL = settings.database_url

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 설정되어 있지 않습니다.")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # 끊어진 커넥션 자동 감지
    pool_size=30,        # Supabase Session mode를 30으로 확대한 값에 맞춤
    max_overflow=0,      # 풀 크기 초과 연결 금지
    pool_timeout=30,     # 풀 고갈 시 대기 시간(초) 후 Timeout
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
