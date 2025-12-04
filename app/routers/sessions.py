from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, Query, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import tempfile
import os

from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.models.session_question import SessionQuestion
from app.models.attempts import Attempt
from app.models.media_asset import MediaAsset
from app.models.basic_question import BasicQuestion
from app.models.generated_question import GeneratedQuestion
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

class UpdateSessionStatusRequest(BaseModel):
    status: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None

@router.post("/{content_id}/sessions/start", include_in_schema=False)
def deprecated_route():
    # 설명용: 실제 경로는 /api/interviews/{id}/sessions/start 이지만
    # main에서 prefix를 /api/sessions 로 잡았으면 아래 엔드포인트를 사용
    return {"message":"use /api/sessions/{content_id}/start"}

@router.post("/{content_id}/start")
def session_start(content_id: int, payload: StartIn):
    if not payload.use_saved_context and not (
        payload.override_context and payload.override_context.questions
    ):
        raise HTTPException(
            status_code=400,
            detail="Provide override_context.questions or enable use_saved_context",
        )
    # TODO: 생성 작업 큐잉
    return {
        "message": "generation_started",
        "session_id": "sess_9a12",
        "generation_id": "gen_73bc",
        "status": "pending",
    }

@router.post("/{session_id}/recordings/{question_index}")
async def upload_recording(
    session_id: int,
    question_index: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    # 1. 세션 존재 및 권한 확인
    session = (
        db.query(InterviewSession)
        .filter(InterviewSession.id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")

    if str(session.user_id) != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    # 1-1. question_index → 실제 SessionQuestion.id 로 매핑
    sq = (
        db.query(SessionQuestion)
        .filter(
            SessionQuestion.session_id == session_id,
            SessionQuestion.order_no == question_index,  # order_no가 1부터면 여기를 question_index + 1 로 바꿔줘
        )
        .first()
    )
    if not sq:
        raise HTTPException(
            status_code=400,
            detail="invalid_question_index_for_session",
        )

    # 2. Attempt 레코드 먼저 생성 (파일명에 attempt.id 사용하기 위해)
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

    # 3. 임시 파일 저장
    tmp_path = None
    try:
        # 파일 내용 읽기
        content = await file.read()

        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # 4. Supabase Storage에 업로드 (attempt.id 포함)
        dest_path = f"sessions/{session_id}/attempt_{attempt.id}.webm"
        storage_path = upload_video(tmp_path, dest_path)

        # 5. MediaAsset 레코드 생성 (video)
        media_video = MediaAsset(
            session_id=session_id,
            attempt_id=attempt.id,
            session_question_id=question_index,
            kind=1,  # video
            storage_url=storage_path
        )
        db.add(media_video)

        # 6. MediaAsset 레코드 생성 (audio) - WebM 파일 동일하게 사용
        media_audio = MediaAsset(
            session_id=session_id,
            attempt_id=attempt.id,
            session_question_id=question_index,
            kind=3,  # audio
            storage_url=storage_path  # 동일한 WebM 파일 사용
        )
        db.add(media_audio)
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
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# 세션 상세 조회 (질문 목록 포함)
@router.get("/{session_id}")
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    # 세션 조회
    session = (
        db.query(InterviewSession)
        .filter(InterviewSession.id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")

    # 권한 확인
    if str(session.user_id) != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    # 세션 질문 조회
    session_questions = (
        db.query(SessionQuestion)
        .filter(SessionQuestion.session_id == session_id)
        .order_by(SessionQuestion.order_no)
        .all()
    )

    # 질문 텍스트 포함
    questions = []
    for sq in session_questions:
        text = None
        question_type_value = None

        # question_type에 따라 적절한 테이블에서 text 가져오기
        if sq.question_type == "BASIC":
            bq = db.get(BasicQuestion, sq.question_id)
            if bq:
                text = bq.text
                question_type_value = bq.type
        elif sq.question_type == "GENERATED":
            gq = db.get(GeneratedQuestion, sq.question_id)
            if gq:
                text = gq.text
                question_type_value = gq.type

        questions.append({
            "id": sq.id,
            "session_id": sq.session_id,
            "question_type": sq.question_type,
            "question_id": sq.question_id,
            "order_no": sq.order_no,
            "text": text,
            "type": question_type_value
        })

    return {
        "id": session.id,
        "user_id": str(session.user_id),
        "content_id": session.content_id,
        "status": session.status,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "question_count": len(questions),
        "session_max": session.session_max,
        "questions": questions,
    }

# 컨텐츠별 세션 목록 조회 (최신순)
@router.get("")
def list_sessions(
    content_id: int = Query(..., description="컨텐츠 ID"),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    sessions = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.content_id == content_id,
            InterviewSession.user_id == user["id"],
        )
        .order_by(InterviewSession.created_at.desc())
        .all()
    )

    return [
        {
            "id": s.id,
            "user_id": str(s.user_id),
            "content_id": s.content_id,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            "session_max": s.session_max,
        }
        for s in sessions
    ]

# 세션 상태 업데이트
@router.patch("/{session_id}/status")
def update_session_status(
    session_id: int,
    payload: UpdateSessionStatusRequest,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    # 세션 조회
    session = (
        db.query(InterviewSession)
        .filter(InterviewSession.id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")

    # 권한 확인
    if str(session.user_id) != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    # 상태 업데이트
    if payload.status is not None:
        # 유효한 status 값 검증
        valid_statuses = ["draft", "running", "done", "canceled"]
        if payload.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        session.status = payload.status

    if payload.started_at is not None:
        session.started_at = datetime.fromisoformat(payload.started_at.replace('Z', '+00:00'))

    if payload.ended_at is not None:
        session.ended_at = datetime.fromisoformat(payload.ended_at.replace('Z', '+00:00'))

    db.commit()
    db.refresh(session)

    return {
        "success": True,
        "session_id": session.id,
        "status": session.status,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
    }

# 사용하지 않는 api 엔드포인트
'''
@router.post("/{session_id}/finish")
def session_finish(session_id: str):
    # TODO: 세션 상태 검증, 기록 집계
    return {"message":"session_finished","record_id":9901,
            "summary":{"score":82,"highlights":["구체적 예시 제시","안정적인 목소리"],
                       "areas_for_improvement":["키 메시지 반복","속도 조절"]}}

'''