import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.config import DATA_DIR
from app.services.expression import analyze_expression_video

router = APIRouter(
    prefix="/api/feedback",
    tags=["expression-feedback"],
)


@router.get("/{session_id}/expression-feedback")
async def expression_feedback(
    session_id: int,
    blink_limit_per_min: int = Query(30, ge=1, le=120),
    baseline_seconds: float = Query(2.0, ge=0.5, le=10.0),
    frame_stride: int = Query(5, ge=1, le=10),
):
    try:
        video_path = os.path.join(DATA_DIR, f"session_{session_id}.mp4")
        if not os.path.exists(video_path):
            alt_path = os.path.join("uploads", f"session_{session_id}.mp4")
            if os.path.exists(alt_path):
                video_path = alt_path
            else:
                raise HTTPException(status_code=404, detail="Session with this ID not found")

        res = analyze_expression_video(
            video_path=video_path,
            blink_limit_per_min=blink_limit_per_min,
            baseline_seconds=baseline_seconds,
            frame_stride=frame_stride
        )

        body = {
            "message": "expression_analysis_success",
            "session_id": session_id,
            "overall_score": res["overall_score"],
            "expression_analysis": {
                "head_eye_gaze_rate": res["expression_analysis"]["head_eye_gaze_rate"] if "expression_analysis" in res else res["head_eye_gaze_rate"],
                "blink_stability":    res["expression_analysis"]["blink_stability"]    if "expression_analysis" in res else res["blink_stability"],
                "mouth_delta":        res["expression_analysis"]["mouth_delta"]        if "expression_analysis" in res else res["mouth_delta"],
                "fixation_metrics":   res["expression_analysis"]["fixation_metrics"]   if "expression_analysis" in res else res["fixation_metrics"],
            } if "expression_analysis" in res else {
                "head_eye_gaze_rate": res["head_eye_gaze_rate"],
                "blink_stability":    res["blink_stability"],
                "mouth_delta":        res["mouth_delta"],
                "fixation_metrics":   res["fixation_metrics"],
            },
            "feedback_summary": res["feedback_summary"]
        }
        return JSONResponse(content=body)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="internal_server_error")