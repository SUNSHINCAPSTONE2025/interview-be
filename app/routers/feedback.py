from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.deps import get_db
from app.services.face_analysis import run_expression_analysis_for_session

router = APIRouter(
    prefix="/api/feedback",
    tags=["expression-feedback"],
)


@router.get("/{session_id}/expression-feedback")
async def expression_feedback(
    session_id: int,
    attempt_id: int = Query(..., description="표정 분석 대상 attempt_id"),
    blink_limit_per_min: int = Query(30, ge=1, le=120),
    baseline_seconds: float = Query(2.0, ge=0.5, le=10.0),
    frame_stride: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    
    try:
        body = await run_expression_analysis_for_session(
            session_id=session_id,
            attempt_id=attempt_id,
            blink_limit_per_min=blink_limit_per_min,
            baseline_seconds=baseline_seconds,
            frame_stride=frame_stride,
            db=db,
        )
        return JSONResponse(content=body)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="internal_server_error")
