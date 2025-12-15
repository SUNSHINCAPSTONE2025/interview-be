# 🧠 NEVER MIND (Interview AI) — Backend

> 사용자의 발화·행동(시선/표정/자세)을 녹화하고, AI 분석으로 즉각적인 정량 피드백을 제공하는 면접 훈련 서비스 (FastAPI)
> 

---

## 1. 서비스 소개

**NEVER MIND**는 실제 면접과 유사한 환경에서 반복 연습이 가능하도록 설계된 AI 면접 훈련 서비스입니다.

사용자는 답변을 녹화/녹음하고, 서버는 음성·시선·표정·자세를 분석해 **점수/등급(양호·보통·개선필요 등) + 요약 피드백**을 제공합니다.

### 핵심 가치

- 자소서/JD 기반 **개인화 질문 생성**
- 발화·행동 분석을 통한 **정량 피드백 제공**
- 피드백 히스토리 기반 **반복 연습/개선 유도**

---

## 2. 프로젝트 구조 및 흐름

### 2-1) 폴더 구조

```
interview-be/
├─ app/
│  ├─ main.py              # FastAPI 앱 엔트리포인트(라우터 등록)
│  ├─ config.py            # 환경변수/설정 로딩
│  ├─ deps.py              # 공통 Depends(인증/DB 등)
│  ├─ db/
│  │  ├─ session.py        # engine/SessionLocal/Base 정의
│  │  └─ base.py           # 공용 DB 세션 export
│  ├─ models/              # DB 모델(SQLAlchemy)
│  │  ├─ attempts.py
│  │  ├─ sessions.py
│  │  ├─ interviews.py
│  │  ├─ basic_question.py
│  │  ├─ generated_question.py
│  │  ├─ session_question.py
│  │  ├─ media_asset.py
│  │  ├─ records.py
│  │  ├─ user_profile.py
│  │  └─ feedback_summary.py
│  ├─ routers/             # API 라우터(HTTP 엔드포인트)
│  │  ├─ auth.py           # 로그인/인증
│  │  ├─ sessions.py       # 세션 생성/진행
│  │  ├─ answers.py        # 답변 저장/조회
│  │  ├─ answer_stt.py     # STT 관련
│  │  ├─ answer_eval.py    # 답변 평가 관련
│  │  ├─ feedback.py       # 음성/표정/자세 피드백 API
│  │  ├─ pose_analysis.py  # 자세 분석 처리
│  │  ├─ records.py        # 기록 조회/저장
│  │  ├─ user_profile.py   # 유저 프로필 관련
│  │  ├─ sessions_voice.py # 세션-음성 연동
│  │  ├─ sessions_pose.py  # 세션-자세 연동
│  │  └─ plans.py
│  └─ services/            # 비즈니스 로직(분석/저장/생성)
│     ├─ feedback_service.py
│     ├─ vocal_feedback.py
│     ├─ vocal_analysis.py
│     ├─ voice_analysis_service.py
│     ├─ face_analysis.py
│     ├─ pose_model.py
│     ├─ stt_service.py
│     ├─ storage_service.py
│     ├─ supa_auth.py
│     ├─ question_generation_service.py
│     └─ resume_qas_service.py
├─ requirements.txt
├─ Dockerfile
├─ render.yaml
├─ .env                    # 로컬에서만 사용(커밋 금지)
└─ README.md
```

### 2-2) 요청 흐름(핵심 시나리오)

**(1) 인증**

1. 프론트에서 로그인(Supabase Auth 등) → Access Token 획득
2. API 호출 시 `Authorization: Bearer <token>` 헤더로 전달
3. 백엔드에서 토큰 검증 → `current_user` 확보

**(2) 면접 세션/시도(Attempt) 생성**

1. 사용자가 연습 시작 → 세션 생성/진행 상태 갱신
2. 질문 선택(기본 질문 + 생성 질문 등) → 세션에 묶어서 제공
3. 사용자가 답변 녹화/녹음 업로드 → Storage 저장 + Attempt 레코드 생성

**(3) 피드백(분석) 요청**

1. 프론트가 attempt별 피드백 API 호출
2. 백엔드가 DB에 기존 분석 결과(FeedbackSummary)가 있으면 즉시 반환
3. 없으면 Storage에서 미디어 다운로드 → 분석 실행 → DB 저장 → 결과 반환

> 피드백은 “즉시 분석(동기)” 형태로 동작하며, 같은 attempt를 다시 조회하면 저장된 결과를 반환하는 방식입니다.
> 

### 2-3) 기능별 코드 위치(찾기 가이드)

- **음성 분석/스코어링 로직**: `app/services/vocal_feedback.py`, `app/services/voice_analysis_service.py`
- **피드백 저장/통합(FeedbackSummary)**: `app/services/feedback_service.py`
- **자세/시선/표정 분석**: `app/services/pose_model.py`, `app/services/face_analysis.py` (프로젝트 구성에 따라 다름)
- **STT(음성→텍스트)**: `app/services/stt_service.py`
- **질문 생성(OpenAI 등)**: `app/services/question_generation_service.py`, `app/services/generation.py`

---

## 3. Tech Stack

- **Language**: Python 3.10+
- **Framework**: FastAPI
- **ASGI Server**: Uvicorn
- **DB**: PostgreSQL (Local Docker 또는 Supabase Postgres)
- **Storage**: Supabase Storage
- **Media Processing**: ffmpeg
- **Auth**: Bearer Token 기반(예: Supabase JWT)

---

## 4. 실행 환경

- OS: Windows 기준(다른 OS도 가능)
- Python: **3.10.x 권장**
- DB: PostgreSQL
- (분석 기능 사용 시) **ffmpeg 설치 필요**

---

## 5. 로컬 실행 방법

### 5-1) 프로젝트 클론 및 이동

```bash
git clone <YOUR_BACKEND_REPO_URL>
cd interview-be
```

### 5-2) 가상환경 생성 및 활성화(Windows)

```bash
py -3.10 -m venv .venv
.\.venv\Scripts\activate
```

PowerShell 실행 정책으로 막히면 1회 실행:

```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 5-3) 패키지 설치

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5-4) 서버 실행

```bash
python -m uvicorn app.main:app --reload
```

- Swagger(OpenAPI): http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

---

## 6. 환경변수(.env) 설정

레포 루트(`interview-be/.env`)에 `.env` 파일을 생성하세요.

⚠️ `.env`는 **절대 커밋하지 않습니다.**

```
# DB
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME

# Supabase (필수로 로딩됨)
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key

# ffmpeg (Windows 예시: 역슬래시 대신 슬래시 권장)
FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe

# OpenAI (질문 생성/평가 기능 사용 시)
OPENAI_API_KEY=sk-...

# Supabase JWT 검증(환경/구성에 따라)
SUPABASE_JWKS_URL=...
SUPABASE_ISSUER=...
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWT_SECRET=...

# Supabase Storage(프로젝트에서 사용하는 경우)
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_STORAGE_URL=...
SUPABASE_VIDEO_BUCKET=videos
SUPABASE_AUDIO_BUCKET=audios

# Google STT 사용 시(프로젝트 구현에 따라)
GOOGLE_STT_KEY_PATH=path/to/google-stt-service-account.json
```

---

## 7. DB 준비

프로젝트는 **PostgreSQL**을 사용합니다.

### 7-1) 로컬 Postgres(Docker) 실행(권장)

```bash
docker run --name interview-postgres ^
  -e POSTGRES_USER=postgres ^
  -e POSTGRES_PASSWORD=postgres ^
  -e POSTGRES_DB=interview ^
  -p 5432:5432 -d postgres:15

```

`.env` 예시:

```
DATABASE_URL=...
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key

```

### 7-2) Supabase(Postgres) 사용(선택)

1. Supabase 프로젝트 생성
2. Database URL(Postgres 연결 문자열) 확인
3. `.env`에 `DATABASE_URL` 반영

### 7-3) 테이블 생성(create_all) (초기 1회)

```bash
python -c "from app.db.session import engine, Base; import app.models.attempts, app.models.sessions, app.models.interviews, app.models.basic_question, app.models.generated_question, app.models.session_question, app.models.media_asset, app.models.records, app.models.user_profile, app.models.feedback_summary; Base.metadata.create_all(bind=engine); print('✅ tables created')"

```

### 7-4) DB 연결 확인(권장)

```bash
python -c "from app.db.session import SessionLocal; from sqlalchemy import text; db=SessionLocal(); db.execute(text('SELECT 1')); db.close(); print('✅ DB connection ok')"

```

### 7-5) (선택) 기본 데이터(Seed) 주입

질문 데이터(`BasicQuestion` 등)가 없으면 세션 시작/질문 선택이 실패할 수 있습니다.

프로젝트에 seed 스크립트가 있다면 실행하거나, DB에 기본 질문을 직접 insert 해주세요.

---

## 8. 실행 확인(필수)

### 8-1) 서버 기동 확인

```bash
python -m uvicorn app.main:app --reload
```

### 8-2) Swagger/OpenAPI 접근 확인

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/openapi.json

---

## 9. Troubleshooting

### 9-1) `uvicorn`을 찾을 수 없음

가상환경 활성화가 안 됐거나 설치가 안 된 경우가 많습니다.

```bash
.\.venv\Scripts\activate
pip show uvicorn
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

### 9-2) DB 오류 / UndefinedTable

- `DATABASE_URL` 확인
- DB가 비어있다면 7-3(create_all) 1회 실행

### 9-3) ffmpeg 관련 오류(분석 기능 실패)

- 설치 확인: `ffmpeg -version`
- Windows라면 `.env`에:

```
FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe
```

---

## 10. ERD / API 문서

- ERD: [CAPSTONE - dbdiagram.io](https://dbdiagram.io/d/CAPSTONE-68dd5c04d2b621e422d4cabd)
- API 문서: `/docs` 참고