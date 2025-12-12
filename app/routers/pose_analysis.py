# app/routers/pose_analysis.py
# 자세 분석 시작(비동기) + 결과 조회

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from tempfile import NamedTemporaryFile
import logging

from app.deps import get_db, get_current_user
from app.db.session import SessionLocal
from app.models.sessions import InterviewSession
from app.models.media_asset import MediaAsset
from app.models.feedback_summary import FeedbackSummary
from app.services.pose_model import run_pose_on_video
from app.services.feedback_service import create_or_update_pose_feedback
from app.services.storage_service import supabase, VIDEO_BUCKET
import os

router = APIRouter()
logger = logging.getLogger(__name__)
# Ensure module logger emits to stdout
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

def _rating_from_score(score: float | None) -> str | None:
    if score is None:
        return None
    try:
        v = float(score)
    except Exception:
        return None
    if v >= 90:
        return "양호"
    if v >= 70:
        return "보통"
    return "미흡"


# POST /api/analysis/pose/start
@router.post("/api/analysis/pose/start", status_code=202)
def start_pose_analysis(
    session_id: int,
    attempt_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # 1) 세션 권한 확인
    session = (
        db.query(InterviewSession)
        .filter(InterviewSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if str(session.user_id) != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    # 2) media 조회 (video kind=1)
    media = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.session_id == session_id,
            MediaAsset.attempt_id == attempt_id,
            MediaAsset.kind == 1,
        )
        .order_by(MediaAsset.created_at.desc())
        .first()
    )

    if not media:
        raise HTTPException(status_code=404, detail="media_not_found")

    storage_path = media.storage_url  # "sessions/11/q1.webm"

    # Supabase Storage에서 파일 다운로드
    try:
        file_bytes: bytes = supabase.storage.from_(VIDEO_BUCKET).download(storage_path)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Failed to download video from storage: {str(e)}",
        )

    # 임시 파일로 저장
    with NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    # Background task: 분석 수행 및 DB 저장
    def _worker(video_path_local: str, s_id: int, a_id: int):
        logger.info("[POSE_ANALYSIS][POST] 백그라운드 분석 시작 session_id=%s attempt_id=%s", s_id, a_id)

        # Context manager로 DB 세션 관리 (자동 close)
        with SessionLocal() as db_session:
            try:
                pose_json = run_pose_on_video(video_path_local)
                logger.info("[POSE_ANALYSIS][POST] 분석 완료, DB 저장 시작 session_id=%s attempt_id=%s", s_id, a_id)
                create_or_update_pose_feedback(db_session, s_id, a_id, pose_json)
                logger.info("[POSE_ANALYSIS][POST] DB 저장 완료 session_id=%s attempt_id=%s", s_id, a_id)
            except Exception as e:
                logger.error("[POSE_ANALYSIS][POST] 백그라운드 분석 에러 session_id=%s attempt_id=%s error=%s", s_id, a_id, str(e))
                logger.exception(e)

        # 임시 파일 삭제 (with 블록 밖에서)
        try:
            os.remove(video_path_local)
        except OSError:
            pass

    background_tasks.add_task(_worker, tmp_path, session_id, attempt_id)

    return {
        "message": "pose_analysis_started",
        "status": "pending",
        "session_id": session_id,
        "attempt_id": attempt_id,
    }


# GET /api/feedback/{session_id}/pose-feedback
@router.get("/api/feedback/{session_id}/pose-feedback")
def get_pose_feedback(
    session_id: int,
    attempt_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # 권한 확인
    session = (
        db.query(InterviewSession)
        .filter(InterviewSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")
    if str(session.user_id) != user["id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    # 결과 조회 (session_id + attempt_id 기준)
    fs = (
        db.query(FeedbackSummary)
        .filter(
            FeedbackSummary.session_id == session_id,
            FeedbackSummary.attempt_id == attempt_id,
        )
        .first()
    )

    import logging
    logger = logging.getLogger(__name__)

    logger.info(
        "[POSE_FEEDBACK][GET] query_result session_id=%s attempt_id=%s fs_exists=%s",
        session_id,
        attempt_id,
        fs is not None,
    )

    # 결과가 있고 값도 있으면 반환
    if fs and fs.overall_pose is not None and fs.shoulder is not None:
        logger.info(
            "[POSE_FEEDBACK][GET] summary_found_with_values session_id=%s attempt_id=%s overall_pose=%s shoulder=%s head=%s hand=%s",
            session_id,
            attempt_id,
            fs.overall_pose,
            fs.shoulder,
            fs.head,
            fs.hand,
        )
        return {
            "message": "pose_analysis_success",
            "session_id": session_id,
            "attempt_id": attempt_id,
            "overall_score": fs.overall_pose,
            "pose_analysis": {
                "overall": {
                    "value": fs.overall_pose,
                    "rating": _rating_from_score(fs.overall_pose),
                },
                "shoulder": {
                    "value": fs.shoulder,
                    "rating": _rating_from_score(fs.shoulder),
                },
                "head_tilt": {
                    "value": fs.head,
                    "rating": _rating_from_score(fs.head),
                },
                "hand": {
                    "value": fs.hand,
                    "rating": _rating_from_score(fs.hand),
                },
            },
            "problem_sections": getattr(fs, "problem_sections", None) or [],
        }

    # 레코드는 있지만 값이 None인 경우
    if fs:
        logger.warning(
            "[POSE_FEEDBACK][GET] summary_exists_but_values_are_null session_id=%s attempt_id=%s → will_analyze",
            session_id,
            attempt_id,
        )

    # 결과가 없거나 값이 None이면 자동으로 분석 시작
    if not fs or fs.overall_pose is None:
        # media 조회 (video kind=1)
        media = (
            db.query(MediaAsset)
            .filter(
                MediaAsset.session_id == session_id,
                MediaAsset.attempt_id == attempt_id,
                MediaAsset.kind == 1,
            )
            .order_by(MediaAsset.created_at.desc())
            .first()
        )

        if not media:
            raise HTTPException(status_code=404, detail="media_not_found")

        storage_path = media.storage_url  # "sessions/11/q1.webm"

        # Supabase Storage에서 파일 다운로드
        try:
            file_bytes: bytes = supabase.storage.from_(VIDEO_BUCKET).download(storage_path)
        except Exception as e:
            raise HTTPException(
                status_code=404,
                detail=f"Failed to download video from storage: {str(e)}",
            )

        # 임시 파일로 저장
        with NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        # Background task: 분석 수행 및 DB 저장
        def _worker(video_path_local: str, s_id: int, a_id: int):
            logger.info("[POSE_ANALYSIS][GET] 백그라운드 분석 시작 session_id=%s attempt_id=%s", s_id, a_id)

            # Context manager로 DB 세션 관리 (자동 close)
            with SessionLocal() as db_session:
                try:
                    logger.info("[POSE_ANALYSIS][GET] run_pose_on_video 시작 session_id=%s attempt_id=%s path=%s", s_id, a_id, video_path_local)
                    pose_json = run_pose_on_video(video_path_local)
                    logger.info("[POSE_ANALYSIS][GET] run_pose_on_video 완료 session_id=%s attempt_id=%s", s_id, a_id)
                    logger.info("[POSE_ANALYSIS][GET] DB 저장 시작 session_id=%s attempt_id=%s", s_id, a_id)
                    create_or_update_pose_feedback(db_session, s_id, a_id, pose_json)
                    logger.info("[POSE_ANALYSIS][GET] DB 저장 완료 session_id=%s attempt_id=%s", s_id, a_id)
                except Exception as e:
                    logger.error("[POSE_ANALYSIS][GET] 백그라운드 분석 에러 session_id=%s attempt_id=%s error=%s", s_id, a_id, str(e))
                    logger.exception(e)

            # 임시 파일 삭제 (with 블록 밖에서)
            try:
                os.remove(video_path_local)
            except OSError:
                pass

        background_tasks.add_task(_worker, tmp_path, session_id, attempt_id)

        # 분석 시작됨 응답 (202 Accepted)
        return JSONResponse(
            status_code=202,
            content={
                "message": "pose_analysis_started",
                "status": "pending",
                "session_id": session_id,
                "attempt_id": attempt_id,
            },
        )
