from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

class QCtx(BaseModel):
    text: str
    prepared_answer: Optional[str] = None

class OverrideContext(BaseModel):
    questions: Optional[List[QCtx]] = None
    selected_mode: Optional[str] = None

class StartIn(BaseModel):
    mode: str
    count: int = 5
    language: str = "ko"
    use_saved_context: bool = True
    override_context: Optional[OverrideContext] = None
    temperature: Optional[float] = 0.7
    seed: Optional[int] = None

@router.post("/{interview_id}/sessions/start", include_in_schema=False)
def deprecated_route():
    # 설명용: 실제 경로는 /api/interviews/{id}/sessions/start 이지만
    # main에서 prefix를 /api/sessions 로 잡았으면 아래 엔드포인트를 사용
    return {"message":"use /api/sessions/{interview_id}/start"}

@router.post("/{interview_id}/start")
def session_start(interview_id: int, payload: StartIn):
    if not payload.use_saved_context and not (payload.override_context and payload.override_context.questions):
        raise HTTPException(status_code=400, detail="Provide override_context.questions or enable use_saved_context")
    # TODO: 생성 작업 큐잉
    return {"message":"generation_started","session_id":"sess_9a12","generation_id":"gen_73bc","status":"pending"}

@router.post("/{session_id}/finish")
def session_finish(session_id: str):
    # TODO: 세션 상태 검증, 기록 집계
    return {"message":"session_finished","record_id":9901,
            "summary":{"score":82,"highlights":["구체적 예시 제시","안정적인 목소리"],
                       "areas_for_improvement":["키 메시지 반복","속도 조절"]}}
