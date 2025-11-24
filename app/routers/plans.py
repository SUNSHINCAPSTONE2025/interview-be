from fastapi import APIRouter, Query
router = APIRouter()

@router.get("/{interview_id}/question-plan/preview")
def question_plan_preview(interview_id: int,
                          mode: str = Query(..., regex="^(tech|soft|both)$"),
                          count: int = 5,
                          language: str = "ko"):
    # TODO: 진행도/연습횟수 고려하여 goal_id/tip_ids 선택
    return {
        "message":"plan_preview",
        "plan":{
            "mode": mode, "question_count": count, "estimated_duration_minutes": count*3,
            "goal_id": "goal_tech_focus" if mode=="tech" else "goal_mixed_focus",
            "tip_ids": ["tip_example","tip_star","tip_followup"]
        }
    }
