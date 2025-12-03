from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as OrmSession

from app.deps import get_db, get_current_user
from app.services.answer_eval import AnswerEvaluationService

router = APIRouter(
    prefix="/api/answer-evaluation",
    tags=["answer-evaluation"],
)

class AnswerEvaluationRequest(BaseModel):
    answer_text: str

class AnswerEvaluationResponse(BaseModel):
    result: Dict[str, Any]

@router.post("", response_model=AnswerEvaluationResponse)
def evaluate_answer_endpoint(
    payload: AnswerEvaluationRequest,
    db: OrmSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    

    result_dict = AnswerEvaluationService.evaluate_answer(payload.answer_text)

    return AnswerEvaluationResponse(result=result_dict).dict()