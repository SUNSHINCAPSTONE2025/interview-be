# app/routers/sessions_voice.py

from typing import Any, Dict
from tempfile import NamedTemporaryFile
import os
import logging

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
from app.services.storage_service import supabase, VIDEO_BUCKET
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/feedback",
    tags=["voice-feedback"],
)


# --- 공통: 세션/오디오 파일 가져오기 ---

def _get_session_or_404(db: OrmSession, session_id: int, user_id: int) -> InterviewSession:
    logger.debug("[VOICE_FEEDBACK] checking session_id=%s user_id=%s", session_id, user_id)
    session_obj = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.id == session_id,
            InterviewSession.user_id == user_id,
        )
        .first()
    )
    if not session_obj:
        logger.warning(
            "[VOICE_FEEDBACK] session_not_found session_id=%s user_id=%s",
            session_id,
            user_id,
        )
        raise HTTPException(status_code=404, detail="Session not found")
    logger.debug(
        "[VOICE_FEEDBACK] session_ok session_id=%s status=%s",
        session_obj.id,
        session_obj.status,
    )
    return session_obj



def _get_audio_storage_url(db: OrmSession, session_id: int, attempt_id: int) -> str:
    logger.debug(
        "[VOICE_FEEDBACK] query_media_asset session_id=%s attempt_id=%s",
        session_id,
        attempt_id,
    )
    q = db.query(MediaAsset).filter(
        MediaAsset.session_id == session_id,
        MediaAsset.kind == 3,  # audio
        MediaAsset.attempt_id == attempt_id,
    )

    asset = q.order_by(MediaAsset.created_at.desc()).first()
    if not asset:
        logger.warning(
            "[VOICE_FEEDBACK] audio_asset_not_found session_id=%s attempt_id=%s",
            session_id,
            attempt_id,
        )
        raise HTTPException(
            status_code=400,
            detail="No audio media asset found for this session/attempt",
        )
    logger.info(
        "[VOICE_FEEDBACK] audio_asset_found session_id=%s attempt_id=%s storage_url=%s",
        session_id,
        attempt_id,
        asset.storage_url,
    )
    return asset.storage_url


# --- 목소리 분석 helper ---

def _analyze_voice(audio_path: str) -> Dict[str, Any]:
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
    current_user=Depends(get_current_user),
):
    logger.info(
        "[VOICE_FEEDBACK][POST] START session_id=%s attempt_id=%s user_id=%s",
        session_id,
        attempt_id,
        current_user["id"],
    )

    # --- 1) 짧은 세션으로 조회만 ---
    with SessionLocal() as db_read:
        _get_session_or_404(db_read, session_id, current_user["id"])
        storage_url = _get_audio_storage_url(db_read, session_id, attempt_id)
    logger.info(
        "[VOICE_FEEDBACK][POST] 20%% audio_path_resolved storage_url=%s",
        storage_url,
    )

    # storage_url → 실제 wav/mp3 로드 → 분석 → payload 생성
    voice_payload = analyze_voice_from_storage_url(storage_url)
    logger.info(
        "[VOICE_FEEDBACK][POST] 70%% analysis_done total_score=%s",
        voice_payload.get("total_score"),
    )

    # feedback_summary 테이블에 overall_voice, tremor, blank, tone, speed, comment 저장
    with SessionLocal() as db_write:
        create_or_update_voice_feedback(db_write, session_id, attempt_id, voice_payload)
    logger.info(
        "[VOICE_FEEDBACK][POST] 100%% feedback_saved session_id=%s attempt_id=%s",
        session_id,
        attempt_id,
    )

    return voice_payload


# --- GET: DB에 저장된 목소리 점수만 조회 ---

@router.get("/{session_id}/voice-feedback", response_model=Dict[str, Any])
def get_voice_feedback_endpoint(
    session_id: int,
    attempt_id: int,
    current_user=Depends(get_current_user),
):
    logger.info(
        "[VOICE_FEEDBACK] START content_id=%s attempt_id=%s user_id=%s",
        session_id,
        attempt_id,
        current_user["id"],
    )

    # --- 1) 짧은 세션으로 조회만 ---
    with SessionLocal() as db_read:
        _get_session_or_404(db_read, session_id, current_user["id"])

        fs = (
            db_read.query(FeedbackSummary)
            .filter(
                FeedbackSummary.session_id == session_id,
                FeedbackSummary.attempt_id == attempt_id,
            )
            .first()
        )

    # 1) 요약이 이미 있고 값도 있으면 그대로 반환
    if fs and fs.overall_voice is not None and fs.tremor is not None:
        logger.info(
            "[VOICE_FEEDBACK][GET] summary_found_with_values session_id=%s attempt_id=%s overall_voice=%s tremor=%s blank=%s tone=%s speed=%s",
            session_id,
            attempt_id,
            fs.overall_voice,
            fs.tremor,
            fs.blank,
            fs.tone,
            fs.speed,
        )
        return build_voice_payload_from_summary(fs)

    # 1-1) 레코드는 있지만 값이 None인 경우
    if fs:
        logger.warning(
            "[VOICE_FEEDBACK][GET] summary_exists_but_values_are_null session_id=%s attempt_id=%s → will_analyze",
            session_id,
            attempt_id,
        )

    # 2) 없으면 자동 분석
    logger.info(
        "[VOICE_FEEDBACK][GET] summary_not_found → auto_analyze session_id=%s attempt_id=%s",
        session_id,
        attempt_id,
    )

    with SessionLocal() as db_read2:
        storage_url = _get_audio_storage_url(db_read2, session_id, attempt_id)
    logger.info(
        "[VOICE_FEEDBACK][GET] audio_storage_url=%s",
        storage_url,
    )

    # Supabase Storage에서 파일 다운로드
    try:
        logger.info(
            "[VOICE_FEEDBACK][GET] 10%% download_from_supabase bucket=%s key=%s",
            VIDEO_BUCKET,
            storage_url,
        )
        file_bytes: bytes = supabase.storage.from_(VIDEO_BUCKET).download(storage_url)
        logger.debug(
            "[VOICE_FEEDBACK][GET] download_ok bytes=%d",
            len(file_bytes) if file_bytes else 0,
        )
    except Exception as e:
        logger.exception(
            "[VOICE_FEEDBACK][GET] download_failed session_id=%s attempt_id=%s",
            session_id,
            attempt_id,
        )
        raise HTTPException(
            status_code=404,
            detail=f"Failed to download audio from storage: {str(e)}",
        )

    # 임시 파일로 저장
    with NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    logger.info(
        "[VOICE_FEEDBACK][GET] 30%% temp_file_created path=%s",
        tmp_path,
    )

    try:
        # 임시 파일 경로로 분석 수행
        voice_payload = analyze_voice_from_storage_url(tmp_path)
        logger.info(
            "[VOICE_FEEDBACK][GET] 80%% analysis_done total_score=%s",
            voice_payload.get("total_score"),
        )

        # feedback_summary 테이블에 저장
        with SessionLocal() as db_write:
            fs_saved = create_or_update_voice_feedback(db_write, session_id, attempt_id, voice_payload)
        logger.info(
            "[VOICE_FEEDBACK][GET] 100%% feedback_saved session_id=%s attempt_id=%s",
            session_id,
            attempt_id,
        )

        return build_voice_payload_from_summary(fs_saved)
    finally:
        # 임시 파일 삭제
        try:
            os.remove(tmp_path)
            logger.debug(
                "[VOICE_FEEDBACK][GET] temp_file_removed path=%s",
                tmp_path,
            )
        except OSError:
            logger.warning(
                "[VOICE_FEEDBACK][GET] temp_file_remove_failed path=%s",
                tmp_path,
            )
