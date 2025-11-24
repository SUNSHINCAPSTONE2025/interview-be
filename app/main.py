# app/main.py
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth as auth_router
from app.routers import interviews as interviews_router
from app.routers import sessions as sessions_router
from app.routers import records as records_router
from app.routers import answers as answers_router
from app.routers import plans as plans_router
from app.routers import user_profile

# 1) FastAPI 앱 생성
app = FastAPI(title="Interview API")

# 2) CORS 미들웨어 추가 (add_middleware 사용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 개발용 전체 허용
    allow_credentials=False,  # 쿠키 안 쓰면 False
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3) 라우터 등록
app.include_router(auth_router.router)
app.include_router(interviews_router.router)
app.include_router(sessions_router.router)
app.include_router(records_router.router)
app.include_router(answers_router.router)
app.include_router(plans_router.router)
app.include_router(user_profile.router)  # ← 프로필 라우터 추가했다면 이 줄도