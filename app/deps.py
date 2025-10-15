# app/deps.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    # FastAPI 의존성: 요청마다 DB 세션 열고 닫기
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # 앱 시작 시 테이블 생성
    # Base 는 user.py 안에 있음. 해당 Base를 모든 모델이 공유하도록 했으므로
    # 모델들을 import 해서 메타데이터에 등록만 해주면 됨!
    from app.models import interviews, sessions  # noqa: F401  (등록 목적)
    from app.models.user import Base
    Base.metadata.create_all(bind=engine)
