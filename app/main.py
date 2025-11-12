# 앱 엔트리포인트
# FastAPI 인스턴스 생성, 라우터 등록 및 DB 초기화, 기본 헬스 체크 루트
from fastapi import FastAPI
from app.deps import init_db
from app.routers import plans, sessions, answers
from app.routers import interviews as interviews_router
from app.routers import auth as auth_router
from app.routers import records as records_router

app = FastAPI()
app.include_router(auth_router.router)
app.include_router(interviews_router.router)
app.include_router(records_router.router)
app.include_router(plans.router,      prefix="/api/interviews", tags=["question-plan"])
app.include_router(sessions.router,   prefix="/api/sessions",   tags=["sessions"])
app.include_router(answers.router,    prefix="/api/sessions",   tags=["answers"])  # answers는 세션 하위

@app.on_event("startup")
def on_startup():
    init_db()
    

@app.get("/")
def root():
    return {"ok": True}
