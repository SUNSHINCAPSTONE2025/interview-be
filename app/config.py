# 설정 모듈
# 환경 변수에서 시크릿키/토큰만료/레이트리밋 값 등을 로드해 전역 설정으로 제공
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "local"
    aws_region: str | None = None
    aws_s3_bucket: str | None = None
    openai_api_key: str | None = None

    database_url: str                        # DATABASE_URL
    supabase_url: str                        # SUPABASE_URL
    supabase_anon_key: str                   # SUPABASE_ANON_KEY
    supabase_jwks_url: str | None = None     # SUPABASE_JWKS_URL  (없으면 코드에서 os.getenv 그대로 써도 됨)
    supabase_issuer: str | None = None       # SUPABASE_ISSUER
    supabase_jwt_audience: str = "authenticated"  # SUPABASE_JWT_AUDIENCE (기본값)

    class Config:
        env_file = ".env"   # 루트 .env 파일에서 위 값들을 읽어옴
        extra = "ignore"

settings = Settings()

