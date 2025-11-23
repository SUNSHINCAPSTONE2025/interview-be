# app/api/sessions.py
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.api_deps import get_db, get_current_user
from app.db.models import InterviewSession, SessionQuestion, Attempt, MediaAsset
from app.services.pose_model import run_pose_on_video
from app.services.feedback_service import create_or_update_pose_feedback
from app.services.storage_service import upload_video, upload_audio, get_signed_url
import os

router = APIRouter()

# 녹화 파일 저장 폴더
RECORDINGS_PATH = "./app/recordings"
os.makedirs(RECORDINGS_PATH, exist_ok=True)  # 서버 실행 시 자동 생성

@router.post("/api/interviews/{interview_id}/sessions/start")
def start_session(
    interview_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    # 1) 세션 생성
    session = InterviewSession(
        user_id=user["id"],
        content_id=interview_id,
        status="running",
        started_at=datetime.now(timezone.utc)
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 2) 세션 질문 생성
    sq = SessionQuestion(
        session_id=session.id,
        question_type="BASIC",
        question_id=0,
        order_no=1
    )
    db.add(sq)
    db.commit()
    db.refresh(sq)

    # 3) attempt 생성
    attempt = Attempt(
        session_id=session.id,
        session_question_id=sq.id,
        status="pending",
        started_at=datetime.now(timezone.utc)
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # ------------------------------
    # 4) Background task: 업로드 + 자세 분석 + 파일 삭제
    # ------------------------------
    def upload_and_analyze(session_id: int, attempt_id: int):
        video_local_path = f"{RECORDINGS_PATH}/session_{session_id}.mp4"
        audio_local_path = f"{RECORDINGS_PATH}/session_{session_id}.wav"

        # 1) Supabase Storage 업로드 (경로만 반환)
        video_path = upload_video(video_local_path, f"session_{session_id}.mp4")
        audio_path = upload_audio(audio_local_path, f"session_{session_id}.wav")

        # 2) DB 저장 (public URL 아님)
        db.add(MediaAsset(session_id=session_id, attempt_id=attempt_id, kind=1, storage_url=video_path))
        db.add(MediaAsset(session_id=session_id, attempt_id=attempt_id, kind=3, storage_url=audio_path))
        db.commit()

        # 3) Signed URL 생성 후 Pose 분석
        signed_video_url = get_signed_url("videos", video_path, 60)
        feedback_json = run_pose_on_video(signed_video_url)
        create_or_update_pose_feedback(db, session_id, feedback_json)

        # 4) 업로드 후 로컬 파일 삭제
        for fpath in [video_local_path, audio_local_path]:
            if os.path.exists(fpath):
                os.remove(fpath)

    background_tasks.add_task(upload_and_analyze, session.id, attempt.id)

    return {
        "message": "session_started",
        "session_id": session.id,
        "question_id": sq.id,
        "attempt_id": attempt.id,
        "status": "running"
    }
