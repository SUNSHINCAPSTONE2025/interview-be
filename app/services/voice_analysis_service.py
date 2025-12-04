# app/services/voice_analysis_service.py

from typing import Dict, Any
import io
import soundfile as sf
from supabase import create_client
import requests
from app.services import vocal_analysis, vocal_feedback
from app.config import settings
import parselmouth

supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
BUCKET_NAME = "interview_media_asset_video"

def _load_sound_from_storage_url(storage_path: str) -> parselmouth.Sound:
    prefix = f"{BUCKET_NAME}/"
    if storage_path.startswith(prefix):
        relative_path = storage_path[len(prefix):]
    else:
        relative_path = storage_path.lstrip("/")

    data: bytes = supabase.storage.from_(BUCKET_NAME).download(relative_path)

    f = io.BytesIO(data)
    y, sr = sf.read(f, dtype="float32", always_2d=True)
    return parselmouth.Sound(y.T, sr)


def _analyze_voice_core(sound) -> Dict[str, Any]:
    """
    실제 분석/스코어링 공통 로직.
    입력만 Praat Sound로 통일해두고,
    어디서든 불러다 쓸 수 있게 따로 뺌.
    """
    tremor = vocal_analysis.eval_tremor(sound)
    sp_tl = vocal_analysis.eval_speed_pause_timeline(sound)
    inton = vocal_analysis.robust_eval_intonation(sound)
    energy = vocal_analysis.eval_energy(sound)
    rhythm = vocal_analysis.eval_rhythm_timing(sound)
    tone = vocal_analysis.compute_tone_fixed(inton, energy, rhythm)

    grouped = vocal_analysis.detect_grouped_with_cfg(sound, tremor, sp_tl)

    payload = vocal_feedback.build_payload_from_structures(tremor, sp_tl, tone)
    payload["grouped"] = grouped
    return payload


def analyze_voice_from_storage_url(storage_url: str) -> Dict[str, Any]:
    """
    MediaAsset.storage_url 을 받아서:
    1) 실제 오디오 로딩 (Supabase URL or 로컬 경로)
    2) vocal_analysis로 프로소디 지표 분석
    3) vocal_feedback으로 프론트용 payload 생성
    """
    sound = _load_sound_from_storage_url(storage_url)
    return _analyze_voice_core(sound)
