# app/services/question_generation_service.py

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.generated_question import GeneratedQuestion
from app.services.create_question import generate_questions_from_qas


def generate_and_store_questions_from_qas(
    db: Session,
    content_id: int,
    qas: List[Dict[str, str]],
    practice_type: Optional[str] = None,
) -> List[GeneratedQuestion]:
    """
    자소서 Q&A 리스트를 받아서:
    1) LLM으로 면접 질문을 생성하고
    2) GeneratedQuestion 테이블에 저장한 후
    3) 방금 저장한 레코드 리스트를 반환

    qas 예시:
    [
        {"question": "지원 동기를 작성해 주세요", "answer": "저는 ..."},
        {"question": "프로젝트 경험을 작성해 주세요", "answer": "졸업 프로젝트에서 ..."},
        ...
    ]
    """

    if not qas:
        raise ValueError("qas is empty")

    llm_result: Dict[str, Any] = generate_questions_from_qas(qas)
    raw_questions: List[Dict[str, Any]] = llm_result.get("questions", [])

    created: List[GeneratedQuestion] = []

    for q in raw_questions:
        text = q.get("text", "").strip()
        q_type = q.get("type") or practice_type or "job"

        if not text:
            continue

        gq = GeneratedQuestion(
            content_id=content_id,
            type=q_type,
            text=text,
            is_used=False,
        )
        db.add(gq)
        created.append(gq)

    db.commit()
    for gq in created:
        db.refresh(gq)

    return created
