# app/services/voice_analysis_service.py

from typing import Dict, Any
import os
import tempfile

import requests
from app.services import vocal_analysis, vocal_feedback


def _load_sound_from_storage_url(storage_url: str):
    """
    storage_url이
      - http/https로 시작하면: 원격에서 다운로드 → 임시 파일에 저장 → load_sound
      - 그 외: 로컬 파일 경로라고 가정하고 바로 load_sound
    """
    if storage_url.startswith("http://") or storage_url.startswith("https://"):
        resp = requests.get(storage_url)
        resp.raise_for_status()

        # Supabase에서 wav/mp3 등 확장자를 그대로 주는 경우가 많으니, 그대로 따옴
        _, ext = os.path.splitext(storage_url)
        if not ext:
            ext = ".wav"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        tmp.write(resp.content)
        tmp.flush()
        tmp.close()

        local_path = tmp.name
    else:
        # 로컬 경로라고 가정 (예: /mnt/audio/..., D:/audio/...)
        local_path = storage_url

    # vocal_analysis.load_sound(path: str) → Praat Sound 객체
    sound = vocal_analysis.load_sound(local_path)
    return sound


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
