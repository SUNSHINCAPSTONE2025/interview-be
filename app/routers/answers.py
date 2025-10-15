from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class MediaIn(BaseModel):
    audio_codec: Optional[str] = "webm/opus"
    video_codec: Optional[str] = "webm/vp9"

class AnswerStartIn(BaseModel):
    question_id: int
    media: MediaIn

@router.post("/{session_id}/answers/start")
def answer_start(session_id: str, payload: AnswerStartIn):
    # TODO: presigned URL 발급
    return {
        "message":"answer_started","answer_id":"ans_abc123",
        "upload":{"audio":{"strategy":"multipart","part_size_mb":5,"presigned_url":"https://..."},
                  "video":{"strategy":"multipart","part_size_mb":8,"presigned_url":"https://..."}}}

@router.post("/{session_id}/answers/{answer_id}/finish")
def answer_finish(session_id: str, answer_id: str):
    # TODO: 업로드 확인 후 STT/음성/자세 분석 트리거
    return {"message":"analysis_started","status":"pending","answer_id":answer_id,
            "pipelines":["stt","voice","posture"]}
