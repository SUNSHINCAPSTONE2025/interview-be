# 1. Python 3.10 기반 이미지 사용
FROM python:3.10-slim

# 2. ffmpeg 설치
RUN apt-get update && apt-get install -y ffmpeg

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 프로젝트 파일 복사
COPY . .

# 5. 파이썬 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 6. FastAPI 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
