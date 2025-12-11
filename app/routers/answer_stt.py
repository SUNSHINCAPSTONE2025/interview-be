from typing import Any, Dict
import tempfile
import os
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.models.attempts import Attempt
from app.models.media_asset import MediaAsset
from app.services.stt_service import STTService
from app.services.storage_service import supabase, VIDEO_BUCKET

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stt",
    tags=["stt"],
)


def _get_session_or_404(db: OrmSession, session_id: int, user_id: int) -> InterviewSession:
    session_obj = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.id == session_id,
            InterviewSession.user_id == user_id,
        )
        .first()
    )
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session_obj


class STTRequest(BaseModel):
    attempt_id: int


class STTResponse(BaseModel):
    session_id: int
    attempt_id: int
    transcript: str


@router.post("/sessions/{session_id}", response_model=STTResponse)
async def transcribe_answer_audio(
    session_id: int,
    payload: STTRequest,
    db: OrmSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    이미 업로드된 오디오 파일을 STT 처리합니다.
    프론트엔드가 파일을 다시 업로드하지 않고, attempt_id만 전달합니다.
    """

    # 세션 권한 체크
    _get_session_or_404(db, session_id, current_user["id"])

    # Attempt 확인
    attempt_obj = (
        db.query(Attempt)
        .filter(
            Attempt.id == payload.attempt_id,
            Attempt.session_id == session_id,
        )
        .first()
    )
    if not attempt_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found",
        )

    # 이미 STT 처리되었는지 확인 (중복 방지)
    if attempt_obj.stt_text:
        return STTResponse(
            session_id=session_id,
            attempt_id=payload.attempt_id,
            transcript=attempt_obj.stt_text,
        )

    # MediaAsset에서 오디오 파일 조회 (kind=3)
    media_asset = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.session_id == session_id,
            MediaAsset.attempt_id == payload.attempt_id,
            MediaAsset.kind == 3,  # audio
        )
        .first()
    )
    if not media_asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found for this attempt",
        )

    # Supabase Storage에서 오디오 파일 다운로드
    try:
        audio_bytes: bytes = supabase.storage.from_(VIDEO_BUCKET).download(media_asset.storage_url)
        if not audio_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Downloaded audio file is empty",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download audio file: {str(e)}",
        )

    # STT 수행
    try:
        logger.info(f"[STT] Starting transcription for attempt_id={payload.attempt_id}")
        transcript = STTService.transcribe(audio_bytes)
        logger.info(f"[STT] Transcription success: {transcript[:50]}...")
    except Exception as e:
        logger.error(f"[STT] Transcription failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"STT processing failed: {str(e)}",
        )

    # 빈 문자열 체크
    if not transcript or transcript.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No speech detected in audio file",
        )

    # transcript 저장
    logger.info(f"[STT] Saving transcript to DB for attempt_id={payload.attempt_id}")
    attempt_obj.stt_text = transcript
    db.add(attempt_obj)
    db.commit()
    db.refresh(attempt_obj)
    logger.info(f"[STT] Successfully saved stt_text: {attempt_obj.stt_text[:50] if attempt_obj.stt_text else 'None'}...")

    return STTResponse(
        session_id=session_id,
        attempt_id=payload.attempt_id,
        transcript=transcript,
    )
