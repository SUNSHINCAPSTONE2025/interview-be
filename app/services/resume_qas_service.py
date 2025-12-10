# app/services/resume_qas_service.py

from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.models.interviews import Resume

def load_resume_qas_for_interview(
    db: Session,
    content_id: int,
    user_id: Optional[str] = None,       # current_user["id"] (uuid string)
) -> List[Dict[str, str]]:
    q = db.query(Resume).filter(Resume.content_id == content_id)

    if user_id is not None:
        q = q.filter(Resume.user_id == user_id)

    rows = q.order_by(Resume.id.asc()).all()

    result: List[Dict[str, str]] = []
    for row in rows:
        if not row.question or not row.answer:
            continue
        result.append(
            {
                "question": row.question,
                "answer": row.answer,
            }
        )

    return result
