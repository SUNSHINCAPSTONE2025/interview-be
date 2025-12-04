# app/routers/answer_eval.py

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.services.answer_eval import AnswerEvaluationService
from app.services.feedback_service import create_or_update_comment_feedback

router = APIRouter(
    prefix="/api/answer-eval",
    tags=["answer-eval"],
)


class AnswerEvalRequest(BaseModel):
    answer_text: str


class AnswerEvalResponse(BaseModel):
    session_id: int
    attempt_id: int
    result: Dict[str, Any]


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session_obj


@router.post("/sessions/{session_id}", response_model=AnswerEvalResponse)
def evaluate_answer_endpoint(
    session_id: int,
    payload: AnswerEvalRequest,
    attempt_id: int = Query(..., description="같은 세션 내 질문 시도 ID"),
    db: OrmSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AnswerEvalResponse:

    # 세션 소유권 확인
    _get_session_or_404(db, session_id, current_user["id"])

    # LLM 평가 실행
    result_dict = AnswerEvaluationService.evaluate_answer(payload.answer_text)

    # comment로 쓸 텍스트 추출 (없으면 빈 문자열)
    comment_text = result_dict.get("overall_summary", "")

    # feedback_summary.comment 저장/업데이트
    create_or_update_comment_feedback(
        db=db,
        session_id=session_id,
        attempt_id=attempt_id,
        comment=comment_text,
    )

    # 프론트로도 평가 결과 전체 반환
    return AnswerEvalResponse(
        session_id=session_id,
        attempt_id=attempt_id,
        result=result_dict,
    )
