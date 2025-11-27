# app/config.py

# ------------------------
# .env 읽기
# ------------------------
from dotenv import load_dotenv
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()  # feat#6 방식 유지: .env 파일 먼저 읽기

# ------------------------
# 프로젝트 루트 계산
# ------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # C:\interviewBE\interview-be

# ------------------------
# Pydantic Settings 정의
# ------------------------
class Settings(BaseSettings):
    # 환경 구분
    app_env: str = "local"

    # AWS
    aws_region: str | None = None
    aws_s3_bucket: str | None = None

    # OpenAI
    openai_api_key: str | None = None

    # Supabase & DB 필수 설정
    database_url: str                        # DATABASE_URL
    supabase_url: str                        # SUPABASE_URL
    supabase_anon_key: str                   # SUPABASE_ANON_KEY
    supabase_jwks_url: str | None = None     # SUPABASE_JWKS_URL
    supabase_issuer: str | None = None       # SUPABASE_ISSUER
    supabase_jwt_audience: str = "authenticated"  # SUPABASE_JWT_AUDIENCE
    supabase_jwt_secret: str | None = None

    # 🔥 pydantic-settings v2 스타일
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),  # 루트 .env 절대경로
        env_file_encoding="utf-8",
        extra="ignore",                   # 필요 없는 env 무시
    )

# ------------------------
# 설정 인스턴스 생성
# ------------------------
settings = Settings()

# ------------------------
# 테스트용: 직접 실행 시
# ------------------------
if __name__ == "__main__":
    print("BASE_DIR:", BASE_DIR)
    print("DATABASE_URL:", settings.database_url)
    print("SUPABASE_URL:", settings.supabase_url)
    print("SUPABASE_ANON_KEY 앞 10글자:", settings.supabase_anon_key[:10], "...")