# app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py 파일 기준으로 프로젝트 루트 계산
BASE_DIR = Path(__file__).resolve().parent.parent  # C:\interviewBE\interview-be

class Settings(BaseSettings):
    app_env: str = "local"
    aws_region: str | None = None
    aws_s3_bucket: str | None = None
    openai_api_key: str | None = None

    # === Supabase & DB 필수 설정 ===
    database_url: str                        # DATABASE_URL
    supabase_url: str                        # SUPABASE_URL
    supabase_anon_key: str                   # SUPABASE_ANON_KEY
    supabase_jwks_url: str | None = None     # SUPABASE_JWKS_URL
    supabase_issuer: str | None = None       # SUPABASE_ISSUER
    supabase_jwt_audience: str = "authenticated"  # SUPABASE_JWT_AUDIENCE
    supabase_jwt_secret: str | None = None   # SUPABASE_JWT_SECRET


    # 🔥 pydantic-settings v2 스타일 설정
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),  # 루트 .env 를 절대경로로 지정
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

if __name__ == "__main__":
    # 테스트용: 값이 제대로 들어오는지 찍어볼 수 있음
    print("BASE_DIR:", BASE_DIR)
    print("DATABASE_URL:", settings.database_url)
    print("SUPABASE_URL:", settings.supabase_url)
    print("SUPABASE_ANON_KEY 앞 10글자:", settings.supabase_anon_key[:10], "...")
