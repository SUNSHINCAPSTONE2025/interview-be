from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.records import PracticeRecord

router = APIRouter(prefix="/api", tags=["records"])


# (1) 마이페이지: 연습 기록 목록
# GET /api/users/{user_id}/records
@router.get("/users/{user_id}/records")
def list_records(
    user_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token_uid = str(current_user["id"])
    if token_uid != str(user_id):
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized to access this resource",
            },
        )

    items = (
        db.query(PracticeRecord)
        .filter(PracticeRecord.user_id == user_id)
        .order_by(PracticeRecord.id.desc())
        .all()
    )
    if not items:
        raise HTTPException(
            status_code=404, detail={"message": "records_not_found"}
        )

    return [
        {
            "id": r.id,
            "interview_id": r.interview_id,
            "company": r.company,
            "position": r.position,
            "d_day": None,  # 필요시 조합
            "progress": None,  # 필요시 조합
            "completed_sessions": None,  # 필요시 조합
            "total_sessions": None,
            "date": r.date.isoformat() if r.date else None,
            "score": r.score,
        }
        for r in items
    ]


# (2) 마이페이지: 피드백 보기
# GET /api/records/{record_id}
@router.get("/records/{record_id}")
def get_record(
    record_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token_uid = str(current_user["id"])

    r = db.query(PracticeRecord).get(record_id)
    if not r:
        raise HTTPException(
            status_code=404, detail={"message": "record_not_found"}
        )
    if str(r.user_id) != token_uid:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized to access this record",
            },
        )

    return {
        "record_id": r.id,
        "interview_id": r.interview_id,
        "company": r.company,
        "position": r.position,
        "category": r.category,
        "date": r.date.isoformat() if r.date else None,
        "score": r.score,
        "questions": r.questions or [],
    }
