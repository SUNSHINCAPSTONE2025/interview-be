# app/db/session.py
# SQLAlchemy 기본 세팅. 프로젝트 DB URL은 환경변수로 설정하세요 (예: DATABASE_URL).
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app import config  # config.py에서 SUPABASE_URL 가져오기

# Supabase 연결용 URL
DATABASE_URL = config.SUPABASE_URL  # .env에 있는 SUPABASE_URL 읽어서 사용db")  # 개발용 sqlite 기본

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()