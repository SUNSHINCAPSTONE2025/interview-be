# 설정 모듈
# 환경 변수에서 시크릿키/토큰만료/레이트리밋 값 등을 로드해 전역 설정으로 제공
from pydantic import BaseSettings

class Settings(BaseSettings):
    app_env: str = "local"
    aws_region: str | None = None
    aws_s3_bucket: str | None = None
    openai_api_key: str | None = None

    class Config:
        env_file = ".env"

settings = Settings()
