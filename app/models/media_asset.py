from sqlalchemy import Column, Integer, BigInteger, Text, String, DateTime, func
from app.db.base import Base

class MediaAsset(Base):

    __tablename__ = "media_asset"

    id = Column(BigInteger, primary_key=True, index=True)
    session_id = Column(BigInteger, index=True, nullable=False)

    attempt_id = Column(BigInteger, nullable=True)
    session_question_id = Column(BigInteger, nullable=True)

    kind = Column(Integer, nullable=False)

    storage_url = Column(Text, nullable=False)
    sha256 = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )