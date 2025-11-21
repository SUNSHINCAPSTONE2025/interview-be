# app/api/sessions.py
# 세션 시작 / attempt 생성 등 — 프론트에서 "연습 시작" 버튼 누르면 호출되는 엔드포인트
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.api_deps import get_db, get_current_user
from app.db.models import InterviewSession, SessionQuestion, Attempt

router = APIRouter()

@router.post("/api/interviews/{interview_id}/sessions/start")
def start_session(interview_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """
    - 인터뷰 아이디로 세션 시작
    - sessions 상태를 'running'으로 변경하고 session_question/attempt 레코드 생성
    - 실제 질문 생성 로직은 간단히 샘플로 둠(추후 질문 생성 서비스 연결)
    """
    # 1) 세션 생성
    session = InterviewSession(
        user_id=user["id"],
        content_id=interview_id,
        status="running",
        started_at=datetime.utcnow()
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # 2) 세션 질문(샘플) 생성 - 실제로는 session_questions 테이블에 여러 질문을 넣음
    sq = SessionQuestion(session_id=session.id, question_type="BASIC", question_id=0, order_no=1)
    db.add(sq)
    db.commit()
    db.refresh(sq)

    # 3) attempt 생성 (질문 1회 응답을 위한 초기 레코드)
    attempt = Attempt(session_id=session.id, session_question_id=sq.id, status="pending", started_at=datetime.utcnow())
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return {
        "message": "session_started",
        "session_id": session.id,
        "question_id": sq.id,
        "attempt_id": attempt.id,
        "status": "running"
    }
