from datetime import date, datetime
from typing import Optional, List, Tuple

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

from app.deps import get_db
from app.models.interviews import Interview, Resume
from app.models.sessions import InterviewSession

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
def _get_session_stats(db: Session, interview_id: int) -> Tuple[int, int]:

    total = (
        db.query(InterviewSession)
        .filter(InterviewSession.interview_id == interview_id)
        .count()
    )

    completed = (
        db.query(InterviewSession)
        .filter(
            InterviewSession.interview_id == interview_id,
            InterviewSession.status == "completed",
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
def list_contents(db: Session = Depends(get_db)):
    items = db.query(Interview).order_by(Interview.id.desc()).all()

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


# 2) 메인: 진행률 업데이트
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



# 3) 메인: 특정 면접 상세 조회
@router.get("/{id}")
def get_interview(id: int, db: Session = Depends(get_db)):
    # i: Optional[Interview] = db.query(Interview).get(id)
    i = db.get(Interview, id)
    if not i:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "interview_not_found",
                "detail": "The interview with the specified ID does not exist",
            },
        )
    return _serialize_interview(i, db)


# 4) 메인: 연습 시작
@router.post("/{id}/sessions/start")
def start_session(id: int, db: Session = Depends(get_db)):
    # i: Optional[Interview] = db.query(Interview).get(id)
    i = db.get(Interview, id)
    if not i:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "interview_not_found",
                "detail": "The interview with the specified ID does not exist",
            },
        )
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
    db.add(s)
    db.commit()
    db.refresh(s)

    return {
        "message": "session_started",
        "session_id": s.id,
        "interview_id": i.id,
        "status": s.status,
    }


# 마이페이지
# A) 마이페이지: 특정 사용자 인터뷰 목록
@router.get("/users/{user_id}/interviews", tags=["mypage"])
def list_user_interviews(
    user_id: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    token_uid = _require_user_id(authorization)
    if token_uid != user_id:
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
    return [_serialize_interview(i, db) for i in items]


# B) 마이페이지: 면접 수정
@router.patch("/{id}", tags=["mypage"])
def update_interview(
    id: int,
    payload: dict = Body(...),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

    # i: Optional[Interview] = db.query(Interview).get(id)
    i = db.get(Interview, id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != token_uid:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized to update this interview",
            },
        )

    # 부분 업데이트
    if "company" in payload:
        if not isinstance(payload["company"], str) or not payload[
            "company"
        ].strip():
            raise HTTPException(
                status_code=400, detail={"message": "invalid_company"}
            )
        i.company = payload["company"].strip()

    if "role" in payload:
        if not isinstance(payload["role"], str) or not payload[
            "role"
        ].strip():
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
            i.interview_date = datetime.strptime(
                payload["interview_date"], "%Y-%m-%d"
            ).date()
        except Exception:
            raise HTTPException(
                status_code=400, detail={"message": "invalid_interview_date"}
            )
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
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

    # i: Optional[Interview] = db.query(Interview).get(id)
    i = db.get(Interview, id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != token_uid:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "forbidden",
                "detail": "User not authorized to delete this interview",
            },
        )

    db.delete(i)
    db.commit()
    db.delete(i)
    db.commit()
    return {"message": "interview_deleted_successfully"}


# 면접 등록 페이지
# 면접 정보 등록: POST /api/interviews/contents
@router.post("/contents", tags=["interviews"])
def create_content(
    payload: dict = Body(...),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_id = str(current_user["id"])

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
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    user_id = _require_user_id(authorization)

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
    if content.user_id != user_id:
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
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != user_id:
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
@router.get("/{interview_id}/question-plan/preview?mode=tech")
def preview_question_plan(
    interview_id: int,
    mode: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    user_id = _require_user_id(authorization)

    # 레이트리밋
    try:
        svc_gen.check_preview_rate(user_id)
    except RuntimeError:
        raise HTTPException(
            status_code=429,
            detail={"message": "rate_limited", "detail": "Too many previews."},
        )

    i = db.query(Interview).get(interview_id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail={"message": "forbidden", "detail": "User not authorized"},
        )

    if mode not in ["tech", "soft", "both"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "invalid_request_query",
                "detail": "mode must be one of ['tech','soft','both']",
            },
        )
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


# 면접 질문 생성 + 세션 시작
@router.post("/{interview_id}/sessions/start", status_code=202)
def start_generation_session(
    interview_id: int,
    payload: dict = Body(...),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    user_id = _require_user_id(authorization)

    # 레이트리밋
    try:
        svc_gen.check_generate_rate(user_id)
    except RuntimeError:
        raise HTTPException(
            status_code=429,
            detail={"message": "rate_limited", "detail": "Too many generations."},
        )

    i = db.query(Interview).get(interview_id)
    if not i:
        raise HTTPException(status_code=404, detail={"message": "interview_not_found"})
    if i.user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail={"message": "forbidden", "detail": "User not authorized"},
        )

    # 중복 실행 방지 (409)
    if svc_gen.is_running(interview_id):
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
            raise HTTPException(
                status_code=413,
                detail={
                    "message": "payload_too_large",
                    "detail": "Max 100 questions",
                },
            )
        for q in questions:
            txt = (q or {}).get("text", "").strip()
            txt = (q or {}).get("text", "").strip()
            if not txt:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "invalid_request_body",
                        "detail": "question.text is required",
                    },
                )
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
                raise HTTPException(
                    status_code=413,
                    detail={
                        "message": "payload_too_large",
                        "detail": "Each question.text ≤ 1000 chars",
                    },
                )

    # 세션 생성(DB) + 실행 마킹
    sess = InterviewSession(interview_id=i.id, status="ongoing")
    db.add(sess)
    db.commit()
    db.refresh(sess)
    db.add(sess)
    db.commit()
    db.refresh(sess)

    # 동시실행 방지 락 세팅
    svc_gen.mark_running(interview_id)

    # 생성 작업 ID들
    session_id, generation_id = svc_gen.new_ids()

    return {
        "message": "generation_started",
        "session_id": session_id,
        "generation_id": generation_id,
        "status": "pending",
        "estimated_duration_minutes": estimated_minutes,
    }

