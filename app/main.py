# app/main.py

# ------------------------
# 환경 변수 로드
# ------------------------
from dotenv import load_dotenv
load_dotenv()

# ------------------------
# FastAPI, CORS 미들웨어 import
# ------------------------
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ------------------------
# dev 브랜치 라우터 import
# ------------------------
from app.routers import auth as auth_router
from app.routers import interviews as interviews_router
from app.routers import sessions as sessions_router
from app.routers import records as records_router
from app.routers import answers as answers_router
from app.routers import plans as plans_router
from app.routers import user_profile as user_profile_router

# ------------------------
# feat#6 라우터 import
# ------------------------
from app.routers import pose_analysis

# ------------------------
# 1) FastAPI 앱 생성
# ------------------------
app = FastAPI(title="Interview API")

# ------------------------
# 2) CORS 미들웨어 추가
#    - 개발용 전체 허용
#    - 실제 운영 시 도메인 제한 필요
# ------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 개발용 전체 허용
    allow_credentials=False,  # 쿠키 안 쓰면 False
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------
# 3) 라우터 등록
#    - dev 브랜치의 기존 서비스 라우터 등록
#    - feat#6 라우터 추가
# ------------------------
app.include_router(auth_router.router)
app.include_router(interviews_router.router)
app.include_router(sessions_router.router)
app.include_router(records_router.router)
app.include_router(answers_router.router)
app.include_router(plans_router.router)
app.include_router(user_profile_router.router)
app.include_router(pose_analysis.router)  # feat#6 추가

# ------------------------
# 4) Root 엔드포인트
#    - feat#6의 health check 용
# ------------------------
@app.get("/")
def root():
    return {"ok": True}