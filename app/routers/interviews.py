from datetime import date, datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Path, Body
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.interviews import Interview
from app.models.sessions import InterviewSession

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


# ---------- 공용 유틸 ----------

def _calc_progress(completed: int, total: int) -> int:
    if total <= 0:
        return 0
    pct = int((completed / total) * 100)
    return max(0, min(100, pct))


def _calc_d_day(interview_date: Optional[date]) -> Optional[int]:
    if not interview_date:
        return None
    return (interview_date - date.today()).days


def _serialize_interview(i: Interview) -> dict:
    return {
        "id": i.id,
        "company": i.company,
        "position": i.position,
        "interview_date": i.interview_date.isoformat() if i.interview_date else None,
        "d_day": _calc_d_day(i.interview_date),
        "progress": _calc_progress(i.completed_sessions, i.total_sessions),
        "completed_sessions": i.completed_sessions,
        "total_sessions": i.total_sessions,
    }


# =========================== 메인 페이지 ====================================
# ---------- 1) 메인: 면접 목록 조회 ----------
@router.get("", response_model=List[dict])
def list_interviews(db: Session = Depends(get_db)):
    items = db.query(Interview).order_by(Interview.id.desc()).all()
    return [_serialize_interview(i) for i in items]


# ---------- 2) 메인: 진행률 업데이트 ----------
@router.patch("/{id}/{progress}")
def update_progress(
    id: int = Path(..., ge=1),
    progress: int = Path(..., ge=0, le=100),
    payload: dict = Body(
        ...,
        examples={
            "default": {
                "summary": "완료 세션 수로 진행률 업데이트 예시",
                "value": {"completed_sessions": 5},
            }
        },
    ),
    db: Session = Depends(get_db),
):
    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "interview_not_found",
                "detail": "The interview with the specified ID does not exist",
            },
        )

    # body 유효성 검사
    if "completed_sessions" not in payload or not isinstance(
        payload["completed_sessions"], int
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_progress_value",
                "detail": "completed_sessions must be an integer",
            },
        )
    new_completed = payload["completed_sessions"]
    if new_completed < 0 or new_completed > i.total_sessions:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_progress_value",
                "detail": "completed_sessions must be between 0 and total_sessions",
            },
        )

    # 업데이트
    i.completed_sessions = new_completed
    db.add(i)
    db.commit()
    db.refresh(i)

    # 실제 진행률을 계산(경로의 {progress}와 불일치해도 계산값을 기준으로 응답)
    computed_progress = _calc_progress(i.completed_sessions, i.total_sessions)

    return {
        "message": "progress_updated_successfully",
        "interview": {
            "id": i.id,
            "progress": computed_progress,
            "completed_sessions": i.completed_sessions,
            "total_sessions": i.total_sessions,
        },
    }


# ---------- 3) 메인: 특정 면접 상세 조회 ----------
@router.get("/{id}")
def get_interview(id: int, db: Session = Depends(get_db)):
    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "interview_not_found",
                "detail": "The interview with the specified ID does not exist",
            },
        )
    return _serialize_interview(i)


# ---------- 4) 메인: 연습 시작 ----------
@router.post("/{id}/sessions/start")
def start_session(id: int, db: Session = Depends(get_db)):
    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "interview_not_found",
                "detail": "The interview with the specified ID does not exist",
            },
        )

    s = InterviewSession(interview_id=i.id, status="ongoing")
    db.add(s)
    db.commit()
    db.refresh(s)

    return {
        "message": "session_started",
        "session_id": s.id,
        "interview_id": i.id,
        "status": s.status,
    }


# ===================== 마이페이지 ============================
# ---------- (A) 특정 사용자 인터뷰 목록 ----------
# GET /api/users/{user_id}/interviews
@router.get("/users/{user_id}/interviews", tags=["mypage"])
def list_user_interviews(
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
        db.query(Interview)
        .filter(Interview.user_id == user_id)
        .order_by(Interview.id.desc())
        .all()
    )
    if not items:
        raise HTTPException(
            status_code=404, detail={"message": "interviews_not_found"}
        )
    return [_serialize_interview(i) for i in items]


# ---------- (B) 면접 수정 ----------
# PATCH /api/interviews/{id}
@router.patch("/{id}")
def update_interview(
    id: int,
    payload: dict = Body(
        ...,
        examples={
            "default": {
                "summary": "면접 정보 수정 예시",
                "value": {
                    "company": "카카오",
                    "position": "백엔드 개발자",
                    "interview_date": "2024-01-30",
                },
            }
        },
    ),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(
            status_code=404, detail={"message": "interview_not_found"}
        )
    if str(i.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized to edit this interview",
            },
        )

    # 부분 업데이트
    if "company" in payload:
        if not isinstance(payload["company"], str) or not payload["company"].strip():
            raise HTTPException(
                status_code=400, detail={"message": "invalid_company"}
            )
        i.company = payload["company"].strip()

    if "position" in payload:
        if not isinstance(payload["position"], str) or not payload["position"].strip():
            raise HTTPException(
                status_code=400, detail={"message": "invalid_position"}
            )
        i.position = payload["position"].strip()

    if "interview_date" in payload and payload["interview_date"] is not None:
        try:
            i.interview_date = datetime.strptime(
                payload["interview_date"], "%Y-%m-%d"
            ).date()
        except Exception:
            raise HTTPException(
                status_code=400, detail={"message": "invalid_interview_date"}
            )
    elif "interview_date" in payload and payload["interview_date"] is None:
        i.interview_date = None

    db.add(i)
    db.commit()
    db.refresh(i)

    return {
        "message": "interview_updated_successfully",
        "interview": _serialize_interview(i),
    }


# ---------- (C) 면접 삭제 ----------
# DELETE /api/interviews/{id}
@router.delete("/{id}")
def delete_interview(
    id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(
            status_code=404, detail={"message": "interview_not_found"}
        )
    if str(i.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized to delete this interview",
            },
        )

    db.delete(i)
    db.commit()
    return {"message": "interview_deleted_successfully"}


# ======================= 면접 등록 페이지 ===============================
# ------------------- (1) 면접 등록 -------------------
@router.post("/register")
def register_interview(
    payload: dict = Body(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

    # 필수값 검증
    required_fields = ["company", "title", "category"]
    if not all(
        field in payload
        and isinstance(payload[field], str)
        and payload[field].strip()
        for field in required_fields
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "fields company, title, category are required",
            },
        )

    company = payload["company"].strip()
    title = payload["title"].strip()
    category = payload["category"].strip()
    interview_date = None

    if "interview_date" in payload and payload["interview_date"]:
        try:
            interview_date = datetime.strptime(
                payload["interview_date"], "%Y-%m-%d"
            ).date()
        except Exception:
            raise HTTPException(
                status_code=400, detail={"message": "invalid_date_format"}
            )

    # 질문 검증
    questions = payload.get("questions", [])
    if not isinstance(questions, list) or len(questions) < 1:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "questions must contain at least one item",
            },
        )

    for q in questions:
        if "text" not in q or not q["text"].strip():
            raise HTTPException(
                status_code=400, detail={"message": "invalid_question_text"}
            )
        if len(q["text"]) > 1000:
            raise HTTPException(
                status_code=413,
                detail={
                    "message": "payload_too_large",
                    "detail": "Max 1000 chars per question",
                },
            )

    # 면접 생성
    interview = Interview(
        user_id=user_id,
        company=company,
        position=title,  # DB 필드명 맞춤 (title -> position)
        interview_date=interview_date,
        total_sessions=10,
        completed_sessions=0,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)

    # 질문 저장 로직 (현재는 DB Table 없음, 가상의 반환 리스트로 대체)
    created_questions = [
        {
            "id": idx + 1,
            "text": q["text"],
            "prepared_answer": q.get("prepared_answer", ""),
        }
        for idx, q in enumerate(questions)
    ]

    d_day = None
    if interview_date:
        d_day = (interview_date - date.today()).days

    return {
        "message": "interview_created_successfully",
        "interview": {
            "id": interview.id,
            "company": interview.company,
            "title": interview.position,
            "category": category,
            "interview_date": interview.interview_date.isoformat()
            if interview.interview_date
            else None,
            "d_day": d_day,
            "registered_at": datetime.utcnow().isoformat() + "Z",
        },
        "created_questions": created_questions,
    }


# ------------------- (2) 면접 질문 유형 선택 -------------------
@router.post("/{interview_id}/question-plan")
def create_question_plan(
    interview_id: int,
    payload: dict = Body(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

    i = db.query(Interview).get(interview_id)
    if not i:
        raise HTTPException(
            status_code=404, detail={"message": "interview_not_found"}
        )
    if str(i.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized for this interview",
            },
        )

    mode = payload.get("mode")
    count = payload.get("count", 5)

    if mode not in ["tech", "soft", "both"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "mode must be one of ['tech','soft','both']",
            },
        )

    if not isinstance(count, int) or not (1 <= count <= 10):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "count must be between 1 and 10",
            },
        )

    # 가상의 질문 생성 (AI 연결 전 stub)
    generated_questions = [f"Sample {mode} question {n+1}" for n in range(count)]

    plan = {
        "mode": mode,
        "goal_id": f"goal_{mode}_beginner",
        "tip_ids": ["tip_star", "tip_example", "tip_followup"],
    }

    return {
        "message": "plan_created",
        "plan": plan,
        "generated_questions": generated_questions,
    }


# ============= 오늘의 목표 & 연습 전 팁 =========================
@router.get("/{interview_id}/question-plan/preview")
def preview_question_plan(
    interview_id: int,
    mode: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

    i = db.query(Interview).get(interview_id)
    if not i:
        raise HTTPException(
            status_code=404, detail={"message": "interview_not_found"}
        )
    if str(i.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized",
            },
        )

    if mode not in ["tech", "soft", "both"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_query",
                "detail": "mode must be one of ['tech','soft','both']",
            },
        )

    # 여기서는 단순히 미리보기용 plan만 반환 (레이트리밋 제거)
    plan = {
        "mode": mode,
        "goal_id": f"goal_{mode}_focus",
        "tip_ids": ["tip_example", "tip_star", "tip_followup"],
    }
    return {"message": "plan_preview", "plan": plan}


# ------------------- 면접 질문 생성 + 세션 시작 -------------------
@router.post("/{interview_id}/sessions/start", status_code=202)
def start_generation_session(
    interview_id: int,
    payload: dict = Body(
        ...,
        examples={
            "default": {
                "summary": "질문 생성 및 세션 시작 요청 예시",
                "value": {
                    "mode": "tech",
                    "count": 5,
                    "language": "ko",
                    "use_saved_context": True,
                    "override_context": {
                        "questions": [
                            {
                                "text": "자기소개를 해주세요.",
                                "prepared_answer": "...",
                            }
                        ]
                    },
                    "selected_mode": "tech",
                    "temperature": 0.7,
                    "seed": None,
                },
            }
        },
    ),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

    i = db.query(Interview).get(interview_id)
    if not i:
        raise HTTPException(
            status_code=404, detail={"message": "interview_not_found"}
        )
    if str(i.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized",
            },
        )

    # ----- 요청 검증 -----
    mode = payload.get("mode")
    count = payload.get("count", 5)
    if mode not in ["tech", "soft", "both"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "Provide one of ['tech','soft','both'] as mode",
            },
        )
    if not isinstance(count, int) or not (1 <= count <= 10):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "count must be 1~10",
            },
        )

    # override_context.questions 검증
    questions = (payload.get("override_context") or {}).get("questions", [])
    if questions:
        if not isinstance(questions, list):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "invalid_request_body",
                    "detail": "questions must be a list",
                },
            )
        if len(questions) > 100:
            raise HTTPException(
                status_code=413,
                detail={
                    "message": "payload_too_large",
                    "detail": "Max 100 questions",
                },
            )
        for q in questions:
            txt = (q or {}).get("text", "").strip()
            if not txt:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "invalid_request_body",
                        "detail": "question.text is required",
                    },
                )
            if len(txt) > 1000:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "message": "payload_too_large",
                        "detail": "Each question.text ≤ 1000 chars",
                    },
                )

    # ----- 세션 생성(DB) -----
    sess = InterviewSession(interview_id=i.id, status="ongoing")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    # svc_gen이 없으니까 간단한 더미 generation_id / 대략 소요시간만 반환
    generation_id = f"gen-{sess.id}"
    estimated_minutes = 5

    return {
        "message": "generation_started",
        "session_id": sess.id,          # 실제 DB 세션 id
        "generation_id": generation_id, # 프론트에서 그냥 표시용
        "status": "pending",
        "estimated_duration_minutes": estimated_minutes,
    }

