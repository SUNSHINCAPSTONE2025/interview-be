# app/routers/answer_eval.py

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from app.deps import get_db, get_current_user
from app.models.sessions import InterviewSession
from app.models.attempts import Attempt
from app.models.feedback_summary import FeedbackSummary
from app.models.session_question import SessionQuestion
from app.models.basic_question import BasicQuestion
from app.models.generated_question import GeneratedQuestion
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


class AttemptFeedbackResponse(BaseModel):
    attempt_id: int
    question_text: Optional[str] = None
    stt_text: Optional[str] = None
    evaluation_comment: Optional[str] = None
    scores: Dict[str, Optional[float]] = {}


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


@router.get("/sessions/{session_id}/attempts/{attempt_id}", response_model=AttemptFeedbackResponse)
def get_attempt_feedback(
    session_id: int,
    attempt_id: int,
    db: OrmSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AttemptFeedbackResponse:
    """
    특정 attempt의 피드백 조회 (STT 텍스트 + 답변 평가 + 점수)
    """

    # 세션 소유권 확인
    _get_session_or_404(db, session_id, current_user["id"])

    # Attempt 조회
    attempt = (
        db.query(Attempt)
        .filter(
            Attempt.id == attempt_id,
            Attempt.session_id == session_id,
        )
        .first()
    )
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found"
        )

    # SessionQuestion 조회 → 질문 텍스트 가져오기
    question_text = None
    session_question = (
        db.query(SessionQuestion)
        .filter(SessionQuestion.session_id == session_id)
        .filter(SessionQuestion.id == attempt.session_question_id)
        .first()
    )

    if session_question:
        # question_type에 따라 실제 질문 텍스트 조회
        if session_question.question_type == "BASIC":
            basic_q = db.get(BasicQuestion, session_question.question_id)
            if basic_q:
                question_text = basic_q.text
        elif session_question.question_type == "GENERATED":
            gen_q = db.get(GeneratedQuestion, session_question.question_id)
            if gen_q:
                question_text = gen_q.text

    # FeedbackSummary 조회
    feedback = (
        db.query(FeedbackSummary)
        .filter(
            FeedbackSummary.session_id == session_id,
            FeedbackSummary.attempt_id == attempt_id,
        )
        .first()
    )

    # 응답 구성
    return AttemptFeedbackResponse(
        attempt_id=attempt_id,
        question_text=question_text,
        stt_text=attempt.stt_text,
        evaluation_comment=feedback.comment if feedback else None,
        scores={
            "overall_voice": float(feedback.overall_voice) if feedback and feedback.overall_voice else None,
            "overall_face": float(feedback.overall_face) if feedback and feedback.overall_face else None,
            "overall_pose": float(feedback.overall_pose) if feedback and feedback.overall_pose else None,
        }
    )
