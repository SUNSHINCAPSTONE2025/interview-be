# app/routers/pose_analysis.py
# 자세 분석 시작(비동기) + 결과 조회

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from tempfile import NamedTemporaryFile

from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.models.media_asset import MediaAsset
from app.models.feedback_summary import FeedbackSummary
from app.services.pose_model import run_pose_on_video
from app.services.feedback_service import create_or_update_pose_feedback
from app.services.storage_service import supabase, VIDEO_BUCKET
import os

router = APIRouter()


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
        try:
            pose_json = run_pose_on_video(video_path_local)
            # feedback_summary(session_id, attempt_id)에 저장되도록 서비스 함수도 같이 수정
            create_or_update_pose_feedback(db, s_id, a_id, pose_json)
        except Exception as e:
            print("pose analysis error:", e)
        finally:
            # 임시 파일 삭제
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

    # 결과가 없으면 자동으로 분석 시작
    if not fs:
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
            try:
                pose_json = run_pose_on_video(video_path_local)
                create_or_update_pose_feedback(db, s_id, a_id, pose_json)
            except Exception as e:
                print("pose analysis error:", e)
            finally:
                # 임시 파일 삭제
                try:
                    os.remove(video_path_local)
                except OSError:
                    pass

        background_tasks.add_task(_worker, tmp_path, session_id, attempt_id)

        # 분석 시작됨 응답 (202 Accepted)
        raise HTTPException(
            status_code=202,
            detail={
                "message": "pose_analysis_started",
                "status": "pending",
                "session_id": session_id,
                "attempt_id": attempt_id,
            }
        )

    # 결과 있음 → 반환
    return {
        "message": "pose_analysis_success",
        "session_id": session_id,
        "attempt_id": attempt_id,
        "overall_score": fs.overall_pose,
        "posture_score": {
            "shoulder": fs.shoulder,
            "head_tilt": fs.head,
            "hand": fs.hand,
        },
        # 필요하면 feedback_summary에 problem_sections(text/json) 컬럼을 추가해서 사용
        "problem_sections": getattr(fs, "problem_sections", None) or [],
    }
