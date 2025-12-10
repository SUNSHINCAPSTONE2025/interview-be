# app/services/voice_analysis_service.py

from typing import Dict, Any
import io, os, tempfile, subprocess
import soundfile as sf
from supabase import create_client
from urllib.parse import urlparse
from app.services import vocal_analysis, vocal_feedback
from app.config import settings
import parselmouth, librosa
import logging

logger = logging.getLogger(__name__)

supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
BUCKET_NAME = "interview_media_asset_video"

def _normalize_supabase_path(raw: str) -> str:
    raw = raw.strip()

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        parts = parsed.path.split("/")
        if BUCKET_NAME in parts:
            idx = parts.index(BUCKET_NAME)
            rel = "/".join(parts[idx + 1 :])
            return rel.lstrip("/")
        return parts[-1]  # 혹시 못 찾으면 파일명만

    prefix = f"{BUCKET_NAME}/"
    if raw.startswith(prefix):
        return raw[len(prefix) :].lstrip("/")

    return raw.lstrip("/")


def _load_sound_from_storage_url(storage_path_or_url: str) -> parselmouth.Sound:
    logger.info("[VOICE] load from storage: %r", storage_path_or_url)

    # 0) 로컬 파일 경로(C:\..., \Users\..., /tmp/...)인 경우 → Supabase 거치지 않고 바로 읽기
    if os.path.isabs(storage_path_or_url):
        logger.debug("[VOICE] detected local path=%r", storage_path_or_url)
        path = storage_path_or_url
        ext = os.path.splitext(path)[1].lower()  # '.webm', '.wav' 등

        # wav → 바로 읽기
        if ext == ".wav":
            y, sr = sf.read(path, dtype="float32", always_2d=True)
            return parselmouth.Sound(y.T, sr)

        # webm/mp4/m4a → ffmpeg로 wav 변환 후 읽기
        if ext in {".webm", ".mp4", ".m4a"}:
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = os.path.join(tmpdir, "output.wav")

                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", path,
                    "-ac", "1",
                    "-ar", "16000",
                    out_path,
                ]
                logger.debug("[VOICE] run ffmpeg(local): %s", " ".join(cmd))
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                if proc.returncode != 0:
                    logger.error(
                        "ffmpeg failed (local): %s",
                        proc.stderr.decode("utf-8", "ignore"),
                    )
                    raise RuntimeError("ffmpeg convert failed (local)")

                y, sr = sf.read(out_path, dtype="float32", always_2d=True)
                return parselmouth.Sound(y.T, sr)

        # 그 외 확장자
        raise RuntimeError(f"Unsupported audio extension (local): {ext}")

    # 1) 로컬 경로가 아니면 → Supabase 경로/URL로 취급
    rel_path = _normalize_supabase_path(storage_path_or_url)
    logger.debug("[VOICE] normalized path=%r", rel_path)

    # Supabase에서 파일 bytes 다운로드
    data: bytes = supabase.storage.from_(BUCKET_NAME).download(rel_path)
    if not data:
        raise RuntimeError(f"Downloaded empty file from storage. path={rel_path!r}")

    ext = os.path.splitext(rel_path)[1].lower()  # '.webm', '.wav' 등

    # 2) 이미 wav인 경우 → 바로 읽기
    if ext == ".wav":
        f = io.BytesIO(data)
        y, sr = sf.read(f, dtype="float32", always_2d=True)
        return parselmouth.Sound(y.T, sr)

    # 3) webm 등인 경우 → ffmpeg로 wav 변환해서 읽기
    if ext in {".webm", ".mp4", ".m4a"}:
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "input" + ext)
            out_path = os.path.join(tmpdir, "output.wav")

            # webm bytes를 임시 파일로 저장
            with open(in_path, "wb") as f:
                f.write(data)

            # ffmpeg로 wav 변환 (예: mono, 16kHz)
            cmd = [
                "ffmpeg",
                "-y",              # 덮어쓰기 허용
                "-i", in_path,     # 입력 파일
                "-ac", "1",        # 채널 수 (mono)
                "-ar", "16000",    # 샘플링 레이트
                out_path,
            ]
            logger.debug("[VOICE] run ffmpeg: %s", " ".join(cmd))
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if proc.returncode != 0:
                logger.error("ffmpeg failed: %s", proc.stderr.decode("utf-8", "ignore"))
                raise RuntimeError("ffmpeg convert failed")

            # 변환된 wav 읽기
            y, sr = sf.read(out_path, dtype="float32", always_2d=True)
            return parselmouth.Sound(y.T, sr)

    # 4) 그 외 확장자
    raise RuntimeError(f"Unsupported audio extension: {ext}")

def _analyze_voice_core(sound) -> Dict[str, Any]:
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
    sound = _load_sound_from_storage_url(storage_url)
    return _analyze_voice_core(sound)
