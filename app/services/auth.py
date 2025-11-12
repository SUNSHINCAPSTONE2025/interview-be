# 인증 관련 로직
# - Pydantic 스키마, 비밀번호 해시/검증, JWT 생성/검증, 이메일 전송 스텁, 간단 레이트리밋 유틸
# 실제 라우팅은 app/routers/auth.py에서 이루어지고, 이 파일은 로직만 담당함.
from fastapi import Header, HTTPException
from datetime import datetime, timedelta
from typing import Optional
import uuid
import jwt # JWT 토큰 인코딩/디코딩
from passlib.context import CryptContext # 비밀번호 해시 처리용
from pydantic import BaseModel, EmailStr, constr
from app.config import settings  # SECRET_KEY 등 config에 추가 필요
from app.routers.services import auth as svc

# bcrypt를 사용해 비밀번호를 안전하게 해시/검증하기 위한 context 객체
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------- Pydantic Schemas ----------
# (FastAPI의 Request Body 검증용)
class SignupIn(BaseModel):
    # 회원가입 요청 시 name, email, password 검증
    name: constr(min_length=1)
    email: EmailStr
    password: constr(min_length=8)

class LoginIn(BaseModel):
    # 로그인 요청 시 email과 password 검증
    email: EmailStr
    password: str

class EmailIn(BaseModel):
    # 이메일 인증 메일 전송이나 비밀번호 찾기 등에서 email만 받을 때 사용
    email: EmailStr

class TokenIn(BaseModel):
    # 이메일 인증 완료나 비밀번호 재설정 등에서 token만 받을 때 사용
    token: str

class PasswordResetIn(BaseModel):
    # 비밀번호 재설정 요청 시 사용하는 스키마
    token: str
    new_password: constr(min_length=8)

class TokenRefreshIn(BaseModel):
    # 리프레시 토큰을 받아 access 토큰 재발급할 때 사용
    refresh_token: str

# ---------- Password ----------
# (비밀번호 해시/검증 함수)
def hash_password(raw: str) -> str:
    # 평문 비밀번호를 bcrypt 알고리즘으로 해시
    return pwd_ctx.hash(raw)

def verify_password(raw: str, hashed: str) -> bool:
    # 입력된 비밀번호(raw)와 저장된 해시가 일치하는지 검증
    return pwd_ctx.verify(raw, hashed)

# ---------- JWT ----------
def _encode(payload: dict) -> str:
    # JWT 페이로드를 시크릿키로 인코딩하여 토큰 생성
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

def _decode(token: str) -> dict:
    # JWT 토큰을 디코딩하여 payload 반환
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

def create_access_token(sub: str) -> str:
    # Access Token 생성
    # 유효기간 : 분 단위
    now = datetime.utcnow()
    payload = {
        "sub": sub, # 사용자 식별자
        "type": "access",
        "iat": int(now.timestamp()), # 발급 시간
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_MIN)).timestamp()), # 만료 시간
    }
    return _encode(payload)

def create_refresh_token(sub: str) -> str:
    # Refresh Token 생성
    # 유효기간 : 일 단위
    # jti(고유 식별자)를 포함하여 추후 무효화 시 관리 가능
    now = datetime.utcnow()
    payload = {
        "sub": sub,
        "type": "refresh",
        "jti": str(uuid.uuid4()), # JWT 고유 ID (로그아웃 시 블랙리스트 처리 등에 활용)
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.REFRESH_TOKEN_DAYS)).timestamp()),
    }
    return _encode(payload)

def decode_token(token: str) -> dict:
    # 토큰을 디코딩하고 payload 반환
    return _decode(token)

# ---------- Email (stub) ----------
# (이메일 전송 - 임시 콘솔 출력 버전)
# 추후 실제 서비스에서는 SMTP 또는 SendGrid로 대체 가능
def send_verification_email(to_email: str, token: str) -> None:
    # 회원가입 후 이메일 인증 링크 전송 (현재는 콘솔 출력)
    print(f"[EMAIL] VERIFY -> {to_email} | token={token}")

def send_password_reset_email(to_email: str, token: str) -> None:
    # 비밀번호 재설정 링크 전송 (현재는 콘솔 출력)
    print(f"[EMAIL] RESET  -> {to_email} | token={token}")

# ---------- Very simple rate limit (in-memory) ----------
# (동일 IP나 계정으로 과도한 로그인 시도 막기)
import time
from collections import defaultdict
# key(email/IP)에 따른 시도 시간 목록 저장
_attempts = defaultdict(list)

def too_many_attempts(key: str, limit: int, window_sec: int) -> bool:
    # 최근 window_sec(초) 동안의 시도 횟수 검사
    # limit 초과하면 True(차단) 반환
    now = time.time()
    _attempts[key] = [t for t in _attempts[key] if now - t < window_sec]
    return len(_attempts[key]) >= limit

def record_attempt(key: str) -> None:
    # 로그인 시도 시간 기록
    _attempts[key].append(time.time())

# 토큰에서 user_id(sub) 뽑기
def _require_user_id(authorization: Optional[str]) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Valid access token required"})
    token = authorization.split()[1]
    try:
        data = svc.decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Invalid token"})
    if data.get("type") != "access":
        raise HTTPException(status_code=401, detail={"message": "unauthorized", "detail": "Access token required"})
    return int(data["sub"])