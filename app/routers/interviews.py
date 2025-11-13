from fastapi import APIRouter, Depends, HTTPException, Path, Body, Header
from typing import Optional, List

from app.schemas.interview import (
    InterviewRegisterRequest,
    InterviewRegisterResponse,
    ContentResponse,
    ResumeResponse
)
from app.services.interview_service import InterviewService
from app.services.interview.generate_interview import GenerateInterviewService

from datetime import date, datetime
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.interviews import Interview
from app.models.sessions import InterviewSession
from app.routers.services import supabase_auth as svc_auth
from app.routers.services import generation as svc_gen

router = APIRouter(prefix="/api/interviews", tags=["interviews"])

# Service 인스턴스
interview_service = InterviewService()
generate_service = GenerateInterviewService()

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

def _require_user_id(authorization: Optional[str]) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Valid access token required"})
    token = authorization.split()[1]
    try:
        data = svc_auth.decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Invalid token"})
    if data.get("type") != "access":
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Access token required"})
    return int(data["sub"])

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
    payload: dict = Body(..., example={"completed_sessions": 5}),
    db: Session = Depends(get_db),
):
    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found",
                                                     "detail": "The interview with the specified ID does not exist"})

    # body 유효성 검사
    if "completed_sessions" not in payload or not isinstance(payload["completed_sessions"], int):
        raise HTTPException(status_code=400, detail={"message": "invalid_progress_value",
                                                     "detail": "completed_sessions must be an integer"})
    new_completed = payload["completed_sessions"]
    if new_completed < 0 or new_completed > i.total_sessions:
        raise HTTPException(status_code=400, detail={"message": "invalid_progress_value",
                                                     "detail": "completed_sessions must be between 0 and total_sessions"})

    # 업데이트
    i.completed_sessions = new_completed
    db.add(i); db.commit(); db.refresh(i)

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
        raise HTTPException(status_code=404, detail={"message": "interview_not_found",
                                                     "detail": "The interview with the specified ID does not exist"})
    return _serialize_interview(i)

# ---------- 4) 메인: 연습 시작 ----------
@router.post("/{id}/sessions/start")
def start_session(id: int, db: Session = Depends(get_db)):
    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found",
                                                     "detail": "The interview with the specified ID does not exist"})

    s = InterviewSession(interview_id=i.id, status="ongoing")
    db.add(s); db.commit(); db.refresh(s)

    return {
        "message": "session_started",
        "session_id": s.id,
        "interview_id": i.id,
        "status": s.status,
    }

# ===================== 마이페이지 ============================
# ---------- (A) 특정 사용자 인터뷰 목록 ----------
# GET /api/users/{user_id}/interviews  -> users_router에 두어도 되지만 여기서 제공
@router.get("/users/{user_id}/interviews", tags=["mypage"])
def list_user_interviews(user_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    token_uid = _require_user_id(authorization)
    if token_uid != user_id:
        raise HTTPException(status_code=403, detail={"message": "forbidden", "detail": "User not authorized to access this resource"})

    items = db.query(Interview).filter(Interview.user_id == user_id).order_by(Interview.id.desc()).all()
    if not items:
        raise HTTPException(status_code=404, detail={"message": "interviews_not_found"})
    return [_serialize_interview(i) for i in items]

# ---------- (B) 면접 수정 ----------
# PATCH /api/interviews/{id}
@router.patch("/{id}")
def update_interview(
    id: int,
    payload: dict = Body(..., example={"company":"카카오","position":"백엔드 개발자","interview_date":"2024-01-30"}),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    token_uid = _require_user_id(authorization)

    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != token_uid:
        raise HTTPException(status_code=403, detail={"message": "forbidden", "detail": "User not authorized to edit this interview"})

    # 부분 업데이트
    if "company" in payload:
        if not isinstance(payload["company"], str) or not payload["company"].strip():
            raise HTTPException(status_code=400, detail={"message": "invalid_company"})
        i.company = payload["company"].strip()

    if "position" in payload:
        if not isinstance(payload["position"], str) or not payload["position"].strip():
            raise HTTPException(status_code=400, detail={"message": "invalid_position"})
        i.position = payload["position"].strip()

    if "interview_date" in payload and payload["interview_date"] is not None:
        try:
            i.interview_date = datetime.strptime(payload["interview_date"], "%Y-%m-%d").date()
        except Exception:
            raise HTTPException(status_code=400, detail={"message": "invalid_interview_date"})
    elif "interview_date" in payload and payload["interview_date"] is None:
        i.interview_date = None

    db.add(i); db.commit(); db.refresh(i)

    return {
        "message": "interview_updated_successfully",
        "interview": _serialize_interview(i),
    }

# ---------- (C) 면접 삭제 ----------
# DELETE /api/interviews/{id}
@router.delete("/{id}")
def delete_interview(
    id: int,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    token_uid = _require_user_id(authorization)

    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != token_uid:
        raise HTTPException(status_code=403, detail={"message": "forbidden", "detail": "User not authorized to delete this interview"})

    db.delete(i); db.commit()
    return {"message": "interview_deleted_successfully"}


# ======================= 면접 등록 페이지 ===============================
# ------------------- (1) 면접 등록 ------------------- (+25.11.12 jiwoo)
@router.post("/register", response_model=InterviewRegisterResponse, status_code=201)
def register_interview(
    payload: InterviewRegisterRequest,
    authorization: Optional[str] = Header(None)
):
    """면접 + 자소서 등록"""
    user_id = _require_user_id(authorization)

    # Service 호출 (비즈니스 로직 위임)
    content, resumes = interview_service.create_interview_with_resumes(
        user_id=user_id,
        company=payload.company,
        role=payload.role,
        role_category=payload.role_category,
        interview_date=payload.interview_date.isoformat(),
        jd_text=payload.jd_text,
        resumes=[{"question": r.question, "answer": r.answer} for r in payload.resumes]
    )

    return {
        "message": "interview_created_successfully",
        "content": ContentResponse(**content),
        "resumes": [ResumeResponse(**r) for r in resumes]
    }

# ------------------- (2) 자소서 기반 면접 질문 생성  ------------------- (+25.11.12 jiwoo)
@router.post("/question")
async def generate_question(
    payload: dict = Body(..., example={
        "content_id": 1,
        "emit_confidence": True,
        "use_seed": False,
        "top_k_seed": 0
    }),
    authorization: Optional[str] = Header(None)
):
    """자소서 기반 면접 질문 생성"""
    user_id = _require_user_id(authorization)

    # 1. 요청 검증
    content_id = payload.get("content_id")
    if not content_id or not isinstance(content_id, int):
        raise HTTPException(status_code=400, detail={"message": "invalid_request_body", "detail": "content_id is required"})

    # 2. 자소서 조회 (InterviewService - 소유권 검증 포함)
    resumes = interview_service.get_resumes_by_content(user_id, content_id)

    # 3. OpenAI 형태로 변환
    qas = interview_service.convert_resumes_to_qas(resumes)

    # 4. AI 질문 생성 (GenerateInterviewService)
    result = await generate_service.generate_from_resume(
        qas=qas,
        emit_confidence=payload.get("emit_confidence", True),
        use_seed=payload.get("use_seed", False),
        top_k_seed=payload.get("top_k_seed", 0)
    )

    return {
        "message": "questions_generated",
        "result": result
    }



# ------------------- (3) 면접 질문 유형 선택 -------------------
@router.post("/{interview_id}/question-plan")
def create_question_plan(
    interview_id: int,
    payload: dict = Body(...),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    user_id = _require_user_id(authorization)
    i = db.query(Interview).get(interview_id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != user_id:
        raise HTTPException(status_code=403, detail={"message": "forbidden", "detail": "User not authorized for this interview"})

    mode = payload.get("mode")
    count = payload.get("count", 5)

    if mode not in ["tech", "soft", "both"]:
        raise HTTPException(status_code=400, detail={"message": "invalid_request_body", "detail": "mode must be one of ['tech','soft','both']"})

    if not isinstance(count, int) or not (1 <= count <= 10):
        raise HTTPException(status_code=400, detail={"message": "invalid_request_body", "detail": "count must be between 1 and 10"})

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
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    user_id = _require_user_id(authorization)

    # 레이트리밋
    try:
        svc_gen.check_preview_rate(user_id)
    except RuntimeError:
        raise HTTPException(status_code=429, detail={"message":"rate_limited", "detail":"Too many previews."})

    i = db.query(Interview).get(interview_id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != user_id:
        raise HTTPException(status_code=403, detail={"message": "forbidden", "detail": "User not authorized"})

    if mode not in ["tech", "soft", "both"]:
        raise HTTPException(status_code=400, detail={"message": "invalid_request_query", "detail": "mode must be one of ['tech','soft','both']"})

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
    payload: dict = Body(..., example={
        "mode":"tech","count":5,"language":"ko","use_saved_context":True,
        "override_context":{"questions":[{"text":"자기소개를 해주세요.","prepared_answer":"..."}]},
        "selected_mode":"tech","temperature":0.7,"seed":None}),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    user_id = _require_user_id(authorization)

    # 레이트리밋
    try:
        svc_gen.check_generate_rate(user_id)
    except RuntimeError:
        raise HTTPException(status_code=429, detail={"message":"rate_limited", "detail":"Too many generations."})

    i = db.query(Interview).get(interview_id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != user_id:
        raise HTTPException(status_code=403, detail={"message": "forbidden", "detail": "User not authorized"})

    # 중복 실행 방지 (409)
    if svc_gen.is_running(interview_id):
        raise HTTPException(status_code=409, detail={"message":"session_already_running"})

    # ----- 요청 검증 -----
    mode = payload.get("mode")
    count = payload.get("count", 5)
    if mode not in ["tech","soft","both"]:
        raise HTTPException(status_code=400, detail={"message":"invalid_request_body","detail":"Provide one of ['tech','soft','both'] as mode"})
    if not isinstance(count, int) or not (1 <= count <= 10):
        raise HTTPException(status_code=400, detail={"message":"invalid_request_body","detail":"count must be 1~10"})

    # override_context.questions 제한(선택)
    questions = (payload.get("override_context") or {}).get("questions", [])
    if questions:
        if not isinstance(questions, list):
            raise HTTPException(status_code=400, detail={"message":"invalid_request_body","detail":"questions must be a list"})
        if len(questions) > 100:
            # 스펙: 413 Payload Too Large
            raise HTTPException(status_code=413, detail={"message":"payload_too_large","detail":"Max 100 questions"})
        for q in questions:
            txt = (q or {}).get("text","").strip()
            if not txt:
                raise HTTPException(status_code=400, detail={"message":"invalid_request_body","detail":"question.text is required"})
            if len(txt) > 1000:
                raise HTTPException(status_code=413, detail={"message":"payload_too_large","detail":"Each question.text ≤ 1000 chars"})

    # ----- 세션 생성(DB) + 실행 마킹 -----
    sess = InterviewSession(interview_id=i.id, status="ongoing")
    db.add(sess); db.commit(); db.refresh(sess)

    # 동시실행 방지 락 세팅 (실제 생성 작업 완료 시 해제하도록 별도 엔드포인트/워커에서 호출)
    svc_gen.mark_running(interview_id)

    # 생성 작업 ID들(비동기 작업 큐가 있다면 여기서 enqueue)
    session_id, generation_id = svc_gen.new_ids()

    return {
        "message": "generation_started",
        "session_id": session_id,      # UI 추적용 (DB의 sess.id와 별개로 예시 제공)
        "generation_id": generation_id,
        "status": "pending",
        "estimated_duration_minutes": svc_gen.estimated_minutes(),
    }