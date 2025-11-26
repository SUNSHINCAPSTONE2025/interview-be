from sqlalchemy import Column, Integer, BigInteger, Text, String, DateTime, func
from app.db.base import Base

class MediaAsset(Base):
    __tablename__ = "media_asset"

    id = Column(BigInteger, primary_key=True, index=True)
    session_id = Column(BigInteger, index=True, nullable=False)
    attempt_id = Column(BigInteger, index=True, nullable=True)
    session_question_id = Column(BigInteger, nullable=True)
    kind = Column(Integer, nullable=False)  # video=1,image=2,audio=3
    storage_url = Column(Text, nullable=False)  # 외부 스토리지 URL 또는 로컬 파일경로
    sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  