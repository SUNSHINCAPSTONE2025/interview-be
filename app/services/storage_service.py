# app/services/storage_service.py
from supabase import create_client
import os
from app.config import settings

SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
VIDEO_BUCKET = os.getenv("SUPABASE_VIDEO_BUCKET")
AUDIO_BUCKET = os.getenv("SUPABASE_AUDIO_BUCKET")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_file_to_supabase(file_path: str, bucket_name: str, dest_path: str) -> str:
    """
    Private Bucket 업로드
    - Supabase Storage에 파일 업로드
    - 반환값: bucket 내의 파일 경로
    """
    with open(file_path, "rb") as f:
        supabase.storage.from_(bucket_name).upload(dest_path, f, {
            "content-type": "application/octet-stream",
            "upsert": True
        })
    return dest_path  # 공개 URL이 아니라 경로만 반환

def upload_video(file_path: str, dest_name: str) -> str:
    return upload_file_to_supabase(file_path, VIDEO_BUCKET, dest_name)

def upload_audio(file_path: str, dest_name: str) -> str:
    return upload_file_to_supabase(file_path, AUDIO_BUCKET, dest_name)

def get_signed_url(bucket: str, path: str, expires: int = 60):
    """
    Private 파일 접근을 위한 Signed URL 생성
    """
    res = supabase.storage.from_(bucket).create_signed_url(path, expires)
    return res.get("signedURL")