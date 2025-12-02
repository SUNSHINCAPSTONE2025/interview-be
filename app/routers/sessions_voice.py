# app/routers/sessions_voice.py

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as OrmSession

from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.models.media_asset import MediaAsset
from app.models.feedback_summary import FeedbackSummary
from app.services.feedback_service import (
    create_or_update_voice_feedback,
    build_voice_payload_from_summary,
)
from app.services import vocal_analysis, vocal_feedback
from app.services.voice_analysis_service import analyze_voice_from_storage_url


router = APIRouter(
    prefix="/api/feedback",
    tags=["voice-feedback"],
)


# --- 공통: 세션/오디오 파일 가져오기 ---

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
        raise HTTPException(status_code=404, detail="Session not found")
    return session_obj



def _get_audio_storage_url(db: OrmSession, session_id: int, attempt_id: int) -> str:
    q = db.query(MediaAsset).filter(
        MediaAsset.session_id == session_id,
        MediaAsset.kind == 3,  # audio
        MediaAsset.attempt_id == attempt_id,
    )

    asset = q.order_by(MediaAsset.created_at.desc()).first()
    if not asset:
        raise HTTPException(
            status_code=400,
            detail="No audio media asset found for this session/attempt",
        )
    return asset.storage_url


# --- 목소리 분석 helper ---

def _analyze_voice(audio_path: str) -> Dict[str, Any]:
    """
    vocal_analysis + vocal_feedback를 한 번에 돌려서
    프론트에서 바로 사용할 payload를 만들어줌.
    payload 구조 예:
      {
        "total_score": 82,
        "summary": "...",
        "metrics": [
          {"id": "tremor", "score": ..., ...},
          {"id": "pause",  "score": ..., ...},
          {"id": "tone",   "score": ..., ...},
          {"id": "speed",  "score": ..., ...},
        ],
        "grouped": {...}  # 선택
      }
    """
    # 1) 음성 로드
    sound = vocal_analysis.load_sound(audio_path)

    # 2) 프로소디 분석
    tremor = vocal_analysis.eval_tremor(sound)
    sp_tl = vocal_analysis.eval_speed_pause_timeline(sound)
    inton = vocal_analysis.robust_eval_intonation(sound)
    energy = vocal_analysis.eval_energy(sound)
    rhythm = vocal_analysis.eval_rhythm_timing(sound)
    tone = vocal_analysis.compute_tone_fixed(inton, energy, rhythm)

    # 3) 문제 구간(grouped) 탐지 (원하면 프론트에서 써도 됨)
    grouped = vocal_analysis.detect_grouped_with_cfg(sound, tremor, sp_tl)

    # 4) 점수 + 요약 payload 생성
    payload = vocal_feedback.build_payload_from_structures(tremor, sp_tl, tone)
    payload["grouped"] = grouped

    return payload


# --- POST: 음성 분석 수행 + DB 반영 ---

@router.post("/{session_id}/voice-feedback", response_model=Dict[str, Any])
def create_or_update_voice_feedback_endpoint(
    session_id: int,
    attempt_id: int,
    db: OrmSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _get_session_or_404(db, session_id, current_user["id"])

    storage_url = _get_audio_storage_url(db, session_id, attempt_id)

    # storage_url → 실제 wav/mp3 로드 → 분석 → payload 생성
    voice_payload = analyze_voice_from_storage_url(storage_url)

    # feedback_summary 테이블에 overall_voice, tremor, blank, tone, speed, comment 저장
    create_or_update_voice_feedback(db, session_id, attempt_id, voice_payload)

    return voice_payload


# --- GET: DB에 저장된 목소리 점수만 조회 ---

@router.get("/{session_id}/voice-feedback", response_model=Dict[str, Any])
def get_voice_feedback_endpoint(
    session_id: int,
    attempt_id: int,
    db: OrmSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _get_session_or_404(db, session_id, current_user["id"])

    fs = (
        db.query(FeedbackSummary)
        .filter(
            FeedbackSummary.session_id == session_id,
            FeedbackSummary.attempt_id == attempt_id,
        )
        .first()
    )
    if not fs:
        raise HTTPException(
            status_code=404,
            detail="Voice feedback not found for this session",
        )

    return build_voice_payload_from_summary(fs)