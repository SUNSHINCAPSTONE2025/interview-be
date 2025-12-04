from datetime import date, datetime, timezone
from typing import Optional, List, Tuple, Dict

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Body,
    Header,
)
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.deps import get_db, get_current_user
from app.models.interviews import Interview, Resume
from app.models.sessions import InterviewSession
from app.models.generated_question import GeneratedQuestion
from app.models.basic_question import BasicQuestion
from app.models.session_question import SessionQuestion
from app.routers import auth as svc_auth
from app.services import generation as svc_gen
from app.services import create_question as svc_question

router = APIRouter(prefix="/api/interviews", tags=["interviews"])

# 진행률 계산 - completed / total -> percent int
def _calc_progress(completed: int, total: int) -> int:
    if total <= 0:
        return 0
    pct = int((completed / total) * 100)
    return max(0, min(100, pct))

# 오늘 기준으로 면접일까지 D-day 계산
def _calc_d_day(interview_date: Optional[date]) -> Optional[int]:
    if not interview_date:
        return None
    return (interview_date - date.today()).days

# 특정 면접의 세션 통계 조회
def _get_session_stats(db: Session, content_id: int) -> Tuple[int, int]:

    total = (
        db.query(InterviewSession)
        .filter(InterviewSession.content_id == content_id)
        .count()
    )

    completed = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.content_id == content_id,
            InterviewSession.status == "done",
        )
        .count()
    )

    return completed, total

# 인터뷰 하나를 응답 JSON으로 변환
def _serialize_interview(i: Interview, db: Session) -> dict:
    completed_sessions, total_sessions = _get_session_stats(db, i.id)
    return {
        "id": i.id,
        "company": i.company,
        # DB 컬럼은 role 이지만 API 응답은 position
        "role": i.role,
        "interview_date": (
            i.interview_date.isoformat() if i.interview_date else None
        ),
        "d_day": _calc_d_day(i.interview_date),
        "progress": _calc_progress(completed_sessions, total_sessions),
        "completed_sessions": completed_sessions,
        "total_sessions": total_sessions,
    }

# 인증 토큰에서 user_id 추출
def _require_user_id(authorization: Optional[str]) -> str:

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={
                "message": "unauthorized",
                "detail": "Valid access token required",
            },
        )
    token = authorization.split()[1]
    try:
        data = svc_auth.decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={"message": "unauthorized", "detail": "Invalid token"},
        )
    if data.get("type") != "access":
        raise HTTPException(
            status_code=401,
            detail={
                "message": "unauthorized",
                "detail": "Access token required",
            },
        )
    # sub 에 uuid 문자열이 들어있다고 가정
    return str(data["sub"])


# 메인 페이지
# 1) 메인: 면접 목록 조회
@router.get("/contents", response_model=List[dict], tags=["interviews"])
def list_contents(
    db: Session = Depends(get_db),
    current = Depends(get_current_user),
):
    user_id = current["id"]
    items = db.query(Interview).filter(Interview.user_id == user_id).order_by(Interview.id.desc()).all()

    results = []
    for i in items:
        completed, total = _get_session_stats(db, i.id)
        results.append(
            {
                "id": i.id,
                "company": i.company,
                "role": i.role,  
                "interview_date": (
                    i.interview_date.isoformat() if i.interview_date else None
                ),
                "completed_sessions": completed,
                "total_sessions": total,
            }
        )
    return results

# 3) 메인: 연습 시작
@router.post("/{id}/sessions/start")
def start_session(
    id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    practice_type = payload.get("practice_type")
    if practice_type not in ["job", "soft"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "practice_type must be one of ['job', 'soft']",
            },
        )

    # 1) 인터뷰 조회
    i = db.get(Interview, id)
    if not i:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "interview_not_found",
                "detail": "The interview with the specified ID does not exist",
            },
        )

    # 2) 질문 뽑기
    basic_questions = (
        db.query(BasicQuestion)
        .filter(BasicQuestion.label == practice_type)
        .order_by(func.random())
        .limit(3)
        .all()
    )
    if len(basic_questions) < 3:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "insufficient_basic_questions",
                "detail": f"Need at least 3 basic questions of type '{practice_type}', "
                          f"found {len(basic_questions)}",
            },
        )

    generated_questions = (
        db.query(GeneratedQuestion)
        .filter(
            GeneratedQuestion.content_id == i.id,
            GeneratedQuestion.is_used == False,
            GeneratedQuestion.type == practice_type,
        )
        .order_by(func.random())
        .limit(2)
        .all()
    )
    if len(generated_questions) < 2:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "insufficient_generated_questions",
                "detail": (
                    f"Need at least 2 unused generated questions of type "
                    f"'{practice_type}' for content_id={i.id}, "
                    f"found {len(generated_questions)}"
                ),
            },
        )

    # payload용 리스트
    all_questions_payload = []

    # 세션에서 사용할 전체 질문 수
    session_max = len(basic_questions) + len(generated_questions)

    # 3) 세션 row 생성 (NOT NULL 필드 다 채우기)
    now = datetime.now(timezone.utc)
    s = InterviewSession(
        user_id=i.user_id,
        content_id=i.id,
        status="draft",
        started_at=now,
        session_max=session_max,
    )
    db.add(s)
    db.flush()  # s.id 확보

    # 4) SessionQuestion 레코드 + payload 구성
    # BasicQuestion
    for order_no, bq in enumerate(basic_questions, start=1):
        sq = SessionQuestion(
            session_id=s.id,
            question_type="BASIC",
            question_id=bq.id,
            order_no=order_no,
        )
        db.add(sq)
        all_questions_payload.append({
            "question_type": "BASIC",
            "question_id": bq.id,
            "order_no": order_no,
            "text": bq.text,
            "type": bq.type,
        })

    # GeneratedQuestion
    for idx, gq in enumerate(generated_questions, start=1):
        order_no = len(basic_questions) + idx
        sq = SessionQuestion(
            session_id=s.id,
            question_type="GENERATED",
            question_id=gq.id,
            order_no=order_no,
        )
        db.add(sq)
        gq.is_used = True  # 재사용 방지

        all_questions_payload.append({
            "question_type": "GENERATED",
            "question_id": gq.id,
            "order_no": order_no,
            "text": gq.text,
            "type": gq.type,
        })

    db.commit()
    db.refresh(s)

    return {
        "message": "session_started",
        "session_id": s.id,
        "content_id": i.id,
        "status": s.status,
        "session_max": session_max,
        "questions": all_questions_payload,
    }

# 면접 등록 페이지
# 면접 정보 등록: POST /api/interviews/contents
@router.post("/contents", tags=["interviews"])
def create_content(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: Dict = Depends(get_current_user),
):
    user_id = current_user["id"]  

    # 필수값 검증
    if (
        "company" not in payload
        or not isinstance(payload["company"], str)
        or not payload["company"].strip()
    ):
        raise HTTPException(
            status_code=400,
            detail={"message": "invalid_request_body", "detail": "company is required"},
        )
    if (
        "role" not in payload
        or not isinstance(payload["role"], str)
        or not payload["role"].strip()
    ):
        raise HTTPException(
            status_code=400,
            detail={"message": "invalid_request_body", "detail": "role is required"},
        )

    company = payload["company"].strip()
    role = payload["role"].strip()
    jd_text = (payload.get("jd_text") or "").strip()

    # role_category: 없으면 0으로
    role_category = payload.get("role_category")
    if role_category is None:
        role_category = 0
    elif not isinstance(role_category, int):
        raise HTTPException(
            status_code=400,
            detail={"message": "invalid_request_body", "detail": "role_category must be int or null"},
        )

    # 면접 날짜 파싱
    interview_date = None
    if payload.get("interview_date"):
        try:
            interview_date = datetime.strptime(
                payload["interview_date"], "%Y-%m-%d"
            ).date()
        except Exception:
            raise HTTPException(
                status_code=400, detail={"message": "invalid_date_format"}
            )

    # DB 저장
    content = Interview(
        user_id=user_id,
        company=company,
        role=role,
        role_category=role_category,
        interview_date=interview_date,
        jd_text=jd_text,
    )
    db.add(content)
    db.commit()
    db.refresh(content)

    return {
        "message": "content_created_successfully",
        "content": {
            "id": content.id,
            "company": content.company,
            "role": content.role,
            "role_category": content.role_category,
            "interview_date": content.interview_date.isoformat()
            if content.interview_date
            else None,
            "jd_text": content.jd_text,
            "created_at": content.created_at.isoformat() if content.created_at else None,
        },
    }


# 자기소개서 등록: POST /api/interviews/resume
@router.post("/resume", tags=["interviews"])
def create_resume(
    payload: dict = Body(...),
    current = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current["id"]

    # 필드 검증
    content_id = payload.get("content_id")
    if not isinstance(content_id, int):
        raise HTTPException(
            status_code=400,
            detail={"message": "invalid_request_body", "detail": "content_id must be int"},
        )

    # content 존재 & 소유자 확인
    content: Optional[Interview] = db.query(Interview).get(content_id)
    if not content:
        raise HTTPException(
            status_code=404, detail={"message": "content_not_found"}
        )
    if str(content.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized for this content",
            },
        )

    version = payload.get("version")
    if version is not None and (not isinstance(version, int) or version <= 0):
        raise HTTPException(
            status_code=400,
            detail={"message": "invalid_request_body", "detail": "version must be positive int"},
        )
    if version is None:
        max_version = (
            db.query(func.max(Resume.version))
            .filter(Resume.content_id == content_id, Resume.user_id == user_id)
            .scalar()
            or 0
        )
        version = max_version + 1

    # items 검증
    items = payload.get("items", [])
    if not isinstance(items, list) or len(items) == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "items must be a non-empty array",
            },
        )

    created_items = []
    for item in items:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=400, detail={"message": "invalid_resume_item"}
            )
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        if not q:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "invalid_resume_item",
                    "detail": "question is required",
                },
            )

        row = Resume(
            user_id=user_id,
            content_id=content_id,
            version=version,
            question=q,
            answer=a,
        )
        db.add(row)
        db.flush()  # id 확보
        created_items.append(
            {"id": row.id, "question": row.question, "answer": row.answer}
        )

    db.commit()

    return {
        "message": "resume_created_successfully",
        "content_id": content_id,
        "version": version,
        "items": created_items,
    }




# 면접 질문 유형 선택
@router.post("/{content_id}/question-plan")
def create_question_plan(
    content_id: int,
    payload: dict = Body(...),
    current = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current["id"]

    i = db.query(Interview).get(content_id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
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

    if mode not in ["job", "soft"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "mode must be one of ['job','soft']",
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

    # 가상의 질문 생성
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


# 오늘의 목표 & 연습 전 팁
@router.get("/{content_id}/question-plan/preview?mode=tech")
def preview_question_plan(
    content_id: int,
    mode: str,
    current = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current["id"]

    # 레이트리밋
    try:
        svc_gen.check_preview_rate(user_id)
    except RuntimeError:
        raise HTTPException(
            status_code=429,
            detail={"message": "rate_limited", "detail": "Too many previews."},
        )

    i = db.query(Interview).get(content_id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if str(i.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={"message": "forbidden", "detail": "User not authorized"},
        )

    if mode not in ["job", "soft", "both"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_query",
                "detail": "mode must be one of ['job','soft','both']",
            },
        )

    plan = {
        "mode": mode,
        "goal_id": f"goal_{mode}_focus",
        "tip_ids": ["tip_example", "tip_star", "tip_followup"],
    }
    return {"message": "plan_preview", "plan": plan}


# 자소서 기반 면접 질문 생성
@router.post("/question", tags=["interviews"])
def create_interview_questions(
    payload: dict = Body(...),
    current = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    자소서 기반 면접 질문 생성
    """
    user_id = current["id"]

    # 필수 파라미터 검증
    if "qas" not in payload or not isinstance(payload["qas"], list):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "qas is required and must be a list",
            },
        )

    if "content_id" not in payload or not isinstance(payload["content_id"], int):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "content_id is required and must be an integer",
            },
        )

    qas = payload["qas"]
    content_id = payload["content_id"]

    # content 존재 및 권한 확인
    content = db.get(Interview, content_id)
    if not content:
        raise HTTPException(
            status_code=404,
            detail={"message": "content_not_found"},
        )
    if str(content.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized for this content",
            },
        )

    # QA 검증
    if len(qas) == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_body",
                "detail": "qas must contain at least one item",
            },
        )

    for qa in qas:
        if not isinstance(qa, dict):
            raise HTTPException(
                status_code=400,
                detail={"message": "invalid_qa_format"},
            )
        if "q" not in qa or "a" not in qa:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "invalid_qa_format",
                    "detail": "Each QA must have 'q' and 'a' fields",
                },
            )

    # 질문 생성
    try:
        result = svc_question.generate_questions_from_qas(qas)
        questions = result.get("questions", [])
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "question_generation_failed",
                "detail": str(e),
            },
        )

    # DB에 저장
    saved_count = 0
    for q in questions:
        question_record = GeneratedQuestion(
            content_id=content_id,
            type=q.get("type", "job"),
            text=q.get("text", ""),
            is_used=False,
        )
        db.add(question_record)
        saved_count += 1

    db.commit()

    return {
        "message": "questions_generated_successfully",
        "content_id": content_id,
        "generated_count": saved_count,
    }


# 면접 질문 생성 + 세션 시작
@router.post("/{content_id}/sessions/start", status_code=202)
def start_generation_session(
    content_id: int,
    payload: dict = Body(...),
    current = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = current["id"]

    # 레이트리밋
    try:
        svc_gen.check_generate_rate(user_id)
    except RuntimeError:
        raise HTTPException(
            status_code=429,
            detail={"message": "rate_limited", "detail": "Too many generations."},
        )

    i = db.query(Interview).get(content_id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if str(i.user_id) != user_id:
        raise HTTPException(
            status_code=403,
            detail={"message": "forbidden", "detail": "User not authorized"},
        )

    # 중복 실행 방지 (409)
    if svc_gen.is_running(content_id):
        raise HTTPException(
            status_code=409, detail={"message": "session_already_running"}
        )

    # 요청 검증
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

    # override_context.questions 제한
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

    # 세션 생성(DB) + 실행 마킹
    sess = InterviewSession(content_id=i.id, status="running")
    db.add(sess)
    db.commit()
    db.refresh(sess)

    # 동시실행 방지 락 세팅
    svc_gen.mark_running(content_id)

    # 생성 작업 ID들
    session_id, generation_id = svc_gen.new_ids()

    return {
        "message": "generation_started",
        "session_id": session_id,
        "generation_id": generation_id,
        "status": "pending",
        "estimated_duration_minutes": svc_gen.estimated_minutes(),
    }

# ===== 사용하지 않는 api =====
'''
# 마이페이지
# A) 마이페이지: 특정 사용자 인터뷰 목록
@router.get("/users/{user_id}/interviews", tags=["mypage"])
async def list_user_interviews(
    user_id: str,
    current = Depends(get_current_user),   
    db: Session = Depends(get_db),
):
    # 1) 토큰의 user_id 와 path 의 user_id가 같은지 체크
    if current["id"] != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized to access this resource",
            },
        )

    # 2) 이 user_id의 인터뷰 조회
    items = (
        db.query(Interview)
        .filter(Interview.user_id == user_id)
        .order_by(Interview.id.desc())
        .all()
    )

    if not items:
        raise HTTPException(
            status_code=404,
            detail={"message": "interviews_not_found"},
        )

    return [_serialize_interview(i, db) for i in items]

# 2) 메인: 진행률 업데이트
@router.patch("/{id}/{progress}")
def update_progress(
        id: int = Path(..., ge=1),
        progress: int = Path(..., ge=0, le=100),  # URL 경로에 있지만 실제 계산에는 안 씀
        payload: dict = Body(...),
        db: Session = Depends(get_db),
):
    # 1) 인터뷰 조회
    i: Optional[Interview] = db.query(Interview).get(id)
    if not i:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "interview_not_found",
                "detail": "The interview with the specified ID does not exist",
            },
        )

    # 2) body 유효성 검사
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

    # 3) 분모: session_max (Interview.sessions 관계에서 가져오기)
    if not i.sessions:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "session_not_found",
                "detail": "No sessions found for this interview",
            },
        )

    # 세션이 여러 개라면 일단 첫 번째 세션 기준으로 사용
    session_row: InterviewSession = i.sessions[0]

    if session_row.session_max is None or session_row.session_max <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_session_max",
                "detail": "session_max must be a positive integer",
            },
        )

    max_sessions = session_row.session_max

    # 4) 완료 세션 개수 범위 체크 (0 ~ session_max)
    if new_completed < 0 or new_completed > max_sessions:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_progress_value",
                "detail": f"completed_sessions must be between 0 and {max_sessions}",
            },
        )

    # 5) 진행도 계산 (분모 = session_max)
    computed_progress = int(new_completed / max_sessions * 100)

    db.add(i)
    db.commit()
    db.refresh(i)

    return {
        "message": "progress_updated_successfully",
        "interview": {
            "id": i.id,
            "progress": computed_progress,        # 계산된 진행도(%)
            "completed_sessions": new_completed,  # 이번 요청에서 받은 값
            "session_max": max_sessions,          # 분모
        },
    }
    
# B) 마이페이지: 면접 수정
@router.patch("/{id}", tags=["mypage"])
def update_interview(
    id: int,
    payload: dict = Body(...),
    current = Depends(get_current_user),   # 🔹 authorization 대신 이거
    db: Session = Depends(get_db),
):
    # 🔹 토큰에서 user_id 가져오는 부분 대체
    token_uid = current["id"]

    # i: Optional[Interview] = db.query(Interview).get(id)
    i = db.get(Interview, id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if str(i.user_id) != token_uid:        # 🔹 타입 맞춰 str() 한 번 감싸는 게 안전
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized to access this resource",
            },
        )

    # 부분 업데이트
    if "company" in payload:
        if not isinstance(payload["company"], str) or not payload["company"].strip():
            raise HTTPException(
                status_code=400, detail={"message": "invalid_company"}
            )
        i.company = payload["company"].strip()

    if "role" in payload:
        if not isinstance(payload["role"], str) or not payload["role"].strip():
            raise HTTPException(
                status_code=400, detail={"message": "invalid_role"}
            )
        # DB에는 role 컬럼으로 저장
        i.role = payload["role"].strip()

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

    completed_sessions, total_sessions = _get_session_stats(db, i.id)

    return {
        "message": "interview_updated_successfully",
        "interview": {
            "id": i.id,
            "company": i.company,
            "role": i.role,
            "interview_date": (
                i.interview_date.isoformat() if i.interview_date else None
            ),
            "progress": _calc_progress(completed_sessions, total_sessions),
            "completed_sessions": completed_sessions,
            "total_sessions": total_sessions,
        },
    }
    
# C) 마이페이지: 면접 삭제
@router.delete("/{id}", tags=["mypage"])
def delete_interview(
    id: int,
    current = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token_uid = current["id"]

    # i: Optional[Interview] = db.query(Interview).get(id)
    i = db.get(Interview, id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if str(i.user_id) != token_uid:
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
'''