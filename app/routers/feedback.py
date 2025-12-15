from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging
import traceback

from app.deps import get_db, get_current_user
from app.services.face_analysis import run_expression_analysis_for_session
from app.services.storage_service import get_signed_url
from app.models.sessions import InterviewSession
from app.models.attempts import Attempt
from app.models.feedback_summary import FeedbackSummary
from app.models.session_question import SessionQuestion
from app.models.basic_question import BasicQuestion
from app.models.generated_question import GeneratedQuestion
from app.models.media_asset import MediaAsset

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/feedback",
    tags=["expression-feedback"],
)


@router.get("/{session_id}/expression-feedback")
async def expression_feedback(
    session_id: int,
    attempt_id: int = Query(..., description="표정 분석 대상 attempt_id"),
    blink_limit_per_min: int = Query(30, ge=1, le=120),
    baseline_seconds: float = Query(2.0, ge=0.5, le=10.0),
    frame_stride: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    
    try:
        body = await run_expression_analysis_for_session(
            session_id=session_id,
            attempt_id=attempt_id,
            blink_limit_per_min=blink_limit_per_min,
            baseline_seconds=baseline_seconds,
            frame_stride=frame_stride,
            db=db,
        )
        return JSONResponse(content=body)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[EXPR_FEEDBACK] Error in expression_feedback: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"internal_server_error: {str(e)}")


def _rating_from_score(score: Optional[float]) -> Optional[str]:
    """점수를 rating 문자열로 변환 (양호/보통/미흡)"""
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


def _rating_from_rate(rate: Optional[float]) -> Optional[str]:
    """0~1 범위 비율을 rating 문자열로 변환"""
    if rate is None:
        return None
    try:
        v = float(rate)
    except Exception:
        return None
    if v >= 0.8:
        return "양호"
    if v >= 0.6:
        return "보통"
    return "개선필요"


@router.get("/{session_id}/attempts/all")
def get_all_attempts_feedback(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    세션의 모든 attempt에 대한 피드백을 한 번에 조회 (DB 저장된 데이터만)

    Returns:
        {
            "session_id": int,
            "attempts": [
                {
                    "attempt_id": int,
                    "question_text": str,
                    "expression": {...},
                    "posture": {...},
                    "voice": {...},
                    "answer_eval": {...}
                }
            ]
        }
    """
    logger.info(
        "[FEEDBACK_ALL] START session_id=%s user_id=%s",
        session_id,
        current_user["id"],
    )

    # 1) 세션 소유권 확인
    session = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user["id"],
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="session_not_found")

    # 2) 세션의 모든 attempt 조회 (시작 시간 순)
    attempts = (
        db.query(Attempt)
        .filter(Attempt.session_id == session_id)
        .order_by(Attempt.started_at)
        .all()
    )

    logger.info(
        "[FEEDBACK_ALL] found %d attempts for session_id=%s",
        len(attempts),
        session_id,
    )

    result_attempts = []

    for attempt in attempts:
        attempt_id = attempt.id

        # 3) 질문 텍스트 가져오기
        question_text = None
        if attempt.session_question_id:
            session_question = db.get(SessionQuestion, attempt.session_question_id)
            if session_question:
                if session_question.question_type == "BASIC":
                    basic_q = db.get(BasicQuestion, session_question.question_id)
                    if basic_q:
                        question_text = basic_q.text
                elif session_question.question_type == "GENERATED":
                    gen_q = db.get(GeneratedQuestion, session_question.question_id)
                    if gen_q:
                        question_text = gen_q.text

        # 4) FeedbackSummary 조회
        feedback = (
            db.query(FeedbackSummary)
            .filter(
                FeedbackSummary.session_id == session_id,
                FeedbackSummary.attempt_id == attempt_id,
            )
            .first()
        )

        # 5) 표정 피드백 구성
        expression_data = None
        if feedback and feedback.overall_face is not None:
            expression_data = {
                "overall_score": float(feedback.overall_face) if feedback.overall_face else None,
                "expression_analysis": {
                    "head_eye_gaze_rate": {
                        "value": float(feedback.gaze) if feedback.gaze else None,
                        "rating": _rating_from_rate(float(feedback.gaze)) if feedback.gaze else None,
                    },
                    "blink_stability": {
                        "value": float(feedback.eye_blink) if feedback.eye_blink else None,
                        "rating": _rating_from_rate(float(feedback.eye_blink)) if feedback.eye_blink else None,
                    },
                    "mouth_delta": {
                        "value": float(feedback.mouth) if feedback.mouth else None,
                        "rating": None,  # mouth_delta는 rating이 다른 방식 (미소/중립/하강)
                    },
                },
                "feedback_summary": "",  # DB에 저장하지 않으므로 빈 문자열
            }

        # 6) 자세 피드백 구성
        posture_data = None
        if feedback and feedback.overall_pose is not None:
            posture_data = {
                "overall_score": float(feedback.overall_pose) if feedback.overall_pose else None,
                "pose_analysis": {
                    "overall": {
                        "value": float(feedback.overall_pose) if feedback.overall_pose else None,
                        "rating": _rating_from_score(float(feedback.overall_pose)) if feedback.overall_pose else None,
                    },
                    "shoulder": {
                        "value": float(feedback.shoulder) if feedback.shoulder else None,
                        "rating": _rating_from_score(float(feedback.shoulder)) if feedback.shoulder else None,
                    },
                    "head_tilt": {
                        "value": float(feedback.head) if feedback.head else None,
                        "rating": _rating_from_score(float(feedback.head)) if feedback.head else None,
                    },
                    "hand": {
                        "value": float(feedback.hand) if feedback.hand else None,
                        "rating": _rating_from_score(float(feedback.hand)) if feedback.hand else None,
                    },
                },
                "problem_sections": [],  # DB에 저장하지 않으므로 빈 배열
            }

        # 7) 목소리 피드백 구성
        voice_data = None
        if feedback and feedback.overall_voice is not None:
            total_score = float(feedback.overall_voice) if feedback.overall_voice else 0.0
            voice_data = {
                "total_score": int(round(total_score)),
                "summary": "",  # DB에 저장하지 않으므로 빈 문자열
                "metrics": [
                    {
                        "id": "tremor",
                        "label": "떨림",
                        "score": float(feedback.tremor) if feedback.tremor else None,
                    },
                    {
                        "id": "pause",
                        "label": "공백",
                        "score": float(feedback.blank) if feedback.blank else None,
                    },
                    {
                        "id": "tone",
                        "label": "억양",
                        "score": float(feedback.tone) if feedback.tone else None,
                    },
                    {
                        "id": "speed",
                        "label": "속도",
                        "score": float(feedback.speed) if feedback.speed else None,
                    },
                ],
            }

        # 8) 답변 평가 구성
        answer_eval_data = {
            "stt_text": attempt.stt_text,
            "evaluation_comment": feedback.comment if feedback else None,
        }

        # 9) attempt 데이터 조합
        attempt_data = {
            "attempt_id": attempt_id,
            "question_text": question_text,
            "expression": expression_data,
            "posture": posture_data,
            "voice": voice_data,
            "answer_eval": answer_eval_data,
        }

        result_attempts.append(attempt_data)

    logger.info(
        "[FEEDBACK_ALL] DONE session_id=%s attempts_count=%d",
        session_id,
        len(result_attempts),
    )

    return {
        "session_id": session_id,
        "attempts": result_attempts,
    }


@router.get("/sessions/{session_id}/attempts/{attempt_id}/video")
def get_attempt_video_url(
    session_id: int,
    attempt_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    특정 attempt의 동영상 signed URL 조회

    Args:
        session_id: 세션 ID
        attempt_id: Attempt ID
        db: DB 세션
        current_user: 현재 사용자 정보

    Returns:
        {
            "session_id": int,
            "attempt_id": int,
            "video_url": str,  # Supabase Storage signed URL
            "expires_in": int  # 초 단위 (3600 = 1시간)
        }

    Raises:
        401: 인증되지 않은 경우
        403: 권한이 없는 경우 (다른 사용자의 세션)
        404: 동영상이 존재하지 않는 경우
    """
    logger.info(
        "[VIDEO_URL] START session_id=%s attempt_id=%s user_id=%s",
        session_id,
        attempt_id,
        current_user["id"],
    )

    # 1) 세션 소유권 확인
    session = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.id == session_id,
            InterviewSession.user_id == current_user["id"],
        )
        .first()
    )
    if not session:
        logger.warning(
            "[VIDEO_URL] Session not found or forbidden: session_id=%s user_id=%s",
            session_id,
            current_user["id"],
        )
        raise HTTPException(
            status_code=403,
            detail="forbidden"
        )

    # 2) MediaAsset에서 동영상 파일 조회 (kind=1: video 또는 kind=3: audio)
    # 같은 .webm 파일이 video(1)와 audio(3)로 중복 등록되므로 둘 다 확인
    media_asset = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.session_id == session_id,
            MediaAsset.attempt_id == attempt_id,
            MediaAsset.kind.in_([1, 3]),  # video(1) 또는 audio(3)
        )
        .first()
    )

    if not media_asset:
        logger.warning(
            "[VIDEO_URL] Video not found: session_id=%s attempt_id=%s",
            session_id,
            attempt_id,
        )
        raise HTTPException(
            status_code=404,
            detail="video_not_found"
        )

    # 3) Supabase Storage Signed URL 생성 (1시간 유효)
    bucket_name = "interview_media_asset_video"
    storage_path = media_asset.storage_url  # 예: "sessions/123/attempt_456.webm"
    expires_in = 3600  # 1시간

    try:
        signed_url = get_signed_url(bucket_name, storage_path, expires_in)

        if not signed_url:
            logger.error(
                "[VIDEO_URL] Failed to generate signed URL: session_id=%s attempt_id=%s path=%s",
                session_id,
                attempt_id,
                storage_path,
            )
            raise HTTPException(
                status_code=500,
                detail="failed_to_generate_signed_url"
            )

        logger.info(
            "[VIDEO_URL] SUCCESS session_id=%s attempt_id=%s",
            session_id,
            attempt_id,
        )

        return {
            "session_id": session_id,
            "attempt_id": attempt_id,
            "video_url": signed_url,
            "expires_in": expires_in,
        }

    except Exception as e:
        logger.error(
            "[VIDEO_URL] Error generating signed URL: %s",
            str(e),
        )
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"internal_server_error: {str(e)}"
        )
