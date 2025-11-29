from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import tempfile
import os

from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.models.attempts import Attempt
from app.models.media_asset import MediaAsset
from app.services.storage_service import upload_video

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

class QCtx(BaseModel):
    text: str
    prepared_answer: Optional[str] = None

class OverrideContext(BaseModel):
    questions: Optional[List[QCtx]] = None
    selected_mode: Optional[str] = None

class StartIn(BaseModel):
    mode: str
    count: int = 5
    language: str = "ko"
    use_saved_context: bool = True
    override_context: Optional[OverrideContext] = None
    temperature: Optional[float] = 0.7
    seed: Optional[int] = None

@router.post("/{content_id}/sessions/start", include_in_schema=False)
def deprecated_route():
    # 설명용: 실제 경로는 /api/interviews/{id}/sessions/start 이지만
    # main에서 prefix를 /api/sessions 로 잡았으면 아래 엔드포인트를 사용
    return {"message":"use /api/sessions/{content_id}/start"}

@router.post("/{content_id}/start")
def session_start(content_id: int, payload: StartIn):
    if not payload.use_saved_context and not (payload.override_context and payload.override_context.questions):
        raise HTTPException(status_code=400, detail="Provide override_context.questions or enable use_saved_context")
    # TODO: 생성 작업 큐잉
    return {"message":"generation_started","session_id":"sess_9a12","generation_id":"gen_73bc","status":"pending"}

@router.post("/{session_id}/finish")
def session_finish(session_id: str):
    # TODO: 세션 상태 검증, 기록 집계
    return {"message":"session_finished","record_id":9901,
            "summary":{"score":82,"highlights":["구체적 예시 제시","안정적인 목소리"],
                       "areas_for_improvement":["키 메시지 반복","속도 조절"]}}


@router.post("/{session_id}/recordings/{question_index}")
async def upload_recording(
    session_id: int,
    question_index: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    질문 녹화 파일 업로드

    FE에서 MediaRecorder로 녹화한 영상(video+audio 통합 webm)을 받아서:
    1. Supabase Storage에 업로드
    2. Attempt 레코드 생성
    3. MediaAsset 레코드 생성

    Args:
        session_id: 세션 ID
        question_index: 질문 번호 (0부터 시작)
        file: 녹화 파일 (webm)

    Returns:
        업로드 성공 정보 (attempt_id, storage_url 등)
    """

    # 1. 세션 존재 및 권한 확인
    session = db.query(InterviewSession).filter(
        InterviewSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")

    if session.user_id != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    # 2. 임시 파일 저장
    tmp_path = None
    try:
        # 파일 내용 읽기
        content = await file.read()

        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # 3. Supabase Storage에 업로드
        dest_path = f"sessions/{session_id}/q{question_index}.webm"
        storage_path = upload_video(tmp_path, dest_path)

        # 4. Attempt 레코드 생성
        # TODO: FE에서 실제 started_at, ended_at, duration_sec 받아오기
        attempt = Attempt(
            session_id=session_id,
            session_question_id=question_index,  # TODO: 실제 session_question_id 매핑
            started_at=datetime.utcnow(),
            ended_at=datetime.utcnow(),
            duration_sec=0,  # TODO: 실제 duration 계산
            status="ok"
        )
        db.add(attempt)
        db.flush()  # attempt.id 생성

        # 5. MediaAsset 레코드 생성 (video)
        media = MediaAsset(
            session_id=session_id,
            attempt_id=attempt.id,
            session_question_id=question_index,
            kind=1,  # video (kind: 1=video, 2=image, 3=audio)
            storage_url=storage_path
        )
        db.add(media)
        db.commit()

        return {
            "success": True,
            "session_id": session_id,
            "question_index": question_index,
            "attempt_id": attempt.id,
            "video_url": storage_path,
            "audio_url": storage_path,  # 현재는 video와 동일 (향후 분리 예정)
            "message": "Recording uploaded successfully"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )

    finally:
        # 임시 파일 삭제
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
