from sqlalchemy import Column, Integer, BigInteger, Text, String, DateTime, ForeignKey, Index, func
from app.db.base import Base

class MediaAsset(Base):
    __tablename__ = "media_asset"

    id = Column(BigInteger, primary_key=True, index=True)
    session_id = Column(BigInteger, ForeignKey("sessions.id"), nullable=False, index=True)
    attempt_id = Column(BigInteger, ForeignKey("attempts.id"), nullable=True, index=True)
    session_question_id = Column(BigInteger, ForeignKey("session_question.id"), nullable=True)
    kind = Column(Integer, nullable=False)  # video=1,image=2,audio=3
    storage_url = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index('ix_media_asset_session_id_created_at', 'session_id', 'created_at'),
    )  