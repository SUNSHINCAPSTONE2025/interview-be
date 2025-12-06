from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.models.attempts import Attempt  
from app.services.stt_service import STTService

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


class STTResponse(BaseModel):
    session_id: int
    attempt_id: int
    transcript: str


@router.post("/sessions/{session_id}", response_model=STTResponse)
async def transcribe_answer_audio(
    session_id: int,
    attempt_id: int = Form(..., description="같은 세션 내 질문 시도 ID"),
    audio_file: UploadFile = File(..., description="사용자 답변 오디오 파일"),
    db: OrmSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:

    # 세션 권한 체크 
    _get_session_or_404(db, session_id, current_user["id"])

    # 파일 타입 체크
    if not audio_file.content_type or not audio_file.content_type.startswith("audio"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audio 형식의 파일만 업로드할 수 있습니다.",
        )

    # 오디오 bytes 로드
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="업로드된 오디오 파일이 비어 있습니다.",
        )

    # STT 수행
    transcript = STTService.transcribe(audio_bytes)

    # 해당 session 내 attempt인지 확인하고 stt_text 저장
    attempt_obj = (
        db.query(Attempt)
        .filter(
            Attempt.id == attempt_id,
            Attempt.session_id == session_id,
        )
        .first()
    )
    if not attempt_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found",
        )

    # transcript 저장
    attempt_obj.stt_text = transcript
    db.add(attempt_obj)
    db.commit()
    db.refresh(attempt_obj)

    return STTResponse(
        session_id=session_id,
        attempt_id=attempt_id,
        transcript=transcript,
    ).dict()