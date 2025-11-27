# app/routers/pose_analysis.py
# 자세 분석 시작(비동기) + 결과 조회

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.models.media_asset import MediaAsset
from app.models.feedback_summary import FeedbackSummary
from app.services.pose_model import run_pose_on_video  # 새로 만든 함수
from app.services.feedback_service import create_or_update_pose_feedback
import os

router = APIRouter()

# POST /api/analysis/pose/start
@router.post("/api/analysis/pose/start", status_code=202)
def start_pose_analysis(session_id: int, attempt_id: int, background_tasks: BackgroundTasks,
                        db: Session = Depends(get_db), user=Depends(get_current_user)):
    """
    1) media_asset에서 해당 session/attempt의 video를 조회
    2) background task로 run_pose_on_video 실행 -> 결과 저장(create_or_update_pose_feedback)
    3) 즉시 202 반환 (analysis started)
    """

    # 1) 세션 권한 확인
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if session.user_id != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    # 2) media 조회 (video kind=1)
    media = db.query(MediaAsset).filter(
        MediaAsset.session_id == session_id,
        MediaAsset.attempt_id == attempt_id,
        MediaAsset.kind == 1
    ).order_by(MediaAsset.created_at.desc()).first()

    if not media:
        raise HTTPException(status_code=404, detail="media_not_found")

    video_path = media.storage_url
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="video_file_not_found_on_server")

    # Background task: 분석 수행 및 DB 저장
    def _worker(video_path_local: str, s_id: int):
        try:
            pose_json = run_pose_on_video(video_path_local)  # 새로 만든 함수 사용
            create_or_update_pose_feedback(db, s_id, pose_json)
        except Exception as e:
            print("pose analysis error:", e)

    background_tasks.add_task(_worker, video_path, session_id)

    return {"message": "pose_analysis_started", "status": "pending", "session_id": session_id}

# GET /api/feedback/{session_id}/pose-feedback
@router.get("/api/feedback/{session_id}/pose-feedback")
def get_pose_feedback(session_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # 권한 확인
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if session.user_id != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    # 결과 조회
    fs = db.query(FeedbackSummary).filter(FeedbackSummary.session_id == session_id).first()
    if not fs:
        raise HTTPException(status_code=409, detail="pose_analysis_not_ready")

    # 명세서에 맞춘 응답 구조
    return {
        "message": "pose_analysis_success",
        "session_id": session_id,
        "overall_score": fs.overall_pose,
        "posture_score": {
            "shoulder": fs.shoulder,
            "head_tilt": fs.head,
            "hand": fs.hand
        },
        "problem_sections": fs.problem_sections or []
    }
