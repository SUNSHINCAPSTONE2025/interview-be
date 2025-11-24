# app/routers/records.py
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.deps import get_db
from app.models.records import PracticeRecord
from app.routers.services import auth as svc

router = APIRouter(prefix="/api", tags=["records"])

def _require_user_id(authorization: Optional[str]) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Valid access token required"})
    token = authorization.split()[1]
    try:
        data = svc.decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Invalid token"})
    if data.get("type") != "access":
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Access token required"})
    return int(data["sub"])

# (1) 마이페이지: 연습 기록 목록
# GET /api/users/{user_id}/records
@router.get("/users/{user_id}/records")
def list_records(user_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    token_uid = _require_user_id(authorization)
    if token_uid != user_id:
        raise HTTPException(status_code=403, detail={"message": "forbidden", "detail": "User not authorized to access this resource"})

    items = db.query(PracticeRecord).filter(PracticeRecord.user_id == user_id).order_by(PracticeRecord.id.desc()).all()
    if not items:
        raise HTTPException(status_code=404, detail={"message": "records_not_found"})
    # 스펙에 맞춰 인터뷰 메타 포함
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
def get_record(record_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    token_uid = _require_user_id(authorization)
    r = db.query(PracticeRecord).get(record_id)
    if not r:
        raise HTTPException(status_code=404, detail={"message":"record_not_found"})
    if r.user_id != token_uid:
        raise HTTPException(status_code=403, detail={"message":"forbidden", "detail":"User not authorized to access this record"})

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
