# # 🧠 NEVER MIND

### AI 기반 면접 훈련 서비스 (Backend)

## 📌 서비스 소개

**NEVER MIND**는 사용자가 자신의 발화와 행동을 녹화하고,

AI 기반 분석을 통해 **즉각적인 정량 피드백**을 받을 수 있는 **면접 훈련 서비스**입니다.

실제 면접과 유사한 환경에서 반복 연습이 가능하도록 설계되었으며,

면접 일정(D-Day)을 기준으로 한 루틴 제공을 통해 **지속적인 성장**을 돕습니다.

### 한 줄 설명

발화를 녹화하고 즉각 피드백을 받는 AI 기반 면접 연습 서비스

### 핵심 가치

- 자기소개서 및 JD 기반 **개인화 질문 생성**
- 발화·행동 분석을 통한 **정량 피드백 제공**
- 면접 일정(D-Day) 기반 **연습 루틴 설계**

### 타깃 사용자

- (현재) 발화 불안을 겪는 신입 / 취업 준비생, 발표 준비가 필요한 대학생
- (확장) 직장인 프레젠테이션, 언어 학습자

### 차별점

- 면접 일정(D-Day) 중심의 구조적 연습 플로우
- 자소서/JD 기반 질문 생성으로 높은 개인화
- 음성(목소리) + 행동(시선·자세·표정) 통합 분석
---

## 0. 목차
- [1. 기술 스택](#1-기술-스택)
- [2. 폴더 구조 및 주요 파일 설명](#2-폴더-구조-및-주요-파일-설명)
- [3. 실행 환경](#3-실행-환경)
- [4. 로컬 실행 방법](#4-로컬-실행-방법)
- [5. 환경변수(.env) 설정](#5-환경변수env-설정)
- [6. DB 준비](#6-db-준비)
- [7. 실행 확인(필수)](#7-실행-확인필수)
- [8. Troubleshooting](#8-troubleshooting)

---

## 1. 기술 스택
- **Python 3.10**
- **FastAPI / Uvicorn**
- **SQLAlchemy + PostgreSQL**
- (선택) **Supabase Storage**
- (분석 기능 사용 시) **ffmpeg**

---

## 2. 폴더 구조 및 주요 파일 설명

### 2-1) 전체 구조
```text
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
└─ .env                    # 로컬에서만 사용(커밋 금지)
```
### 2-2) 요청 흐름(Request Flow)

아래는 **사용자가 면접을 시작해서 피드백을 확인하기까지**의 전체 흐름입니다.  
(각 단계는 실제 라우터/서비스 파일과 1:1로 대응되도록 정리했습니다.)

#### A. 인증(로그인)
1) **로그인 요청**
- `app/routers/auth.py`
- 목적: access token 발급 및 사용자 식별

#### B. 세션 생성 및 질문 구성
2) **세션 시작 / 질문 세팅**
- `app/routers/sessions.py`
- 내부 동작(예시):
  - practice_type에 따라 질문 선택
  - BasicQuestion / GeneratedQuestion 조합
  - SessionQuestion에 저장

3) **세션 상세 조회 / 진행 관리**
- `app/routers/sessions.py`
- 목적: 진행 중인 세션 상태, 질문 리스트, attempt 목록 등 조회

#### C. 답변(Attempt) 생성 및 업로드
4) **답변(Attempt) 생성**
- `app/routers/answers.py`
- 목적: 질문에 대한 사용자 답변 시도(Attempt) 레코드 생성

5) **음성/영상 파일 업로드 및 저장**
- (프로젝트 구성에 따라)
  - Storage URL을 DB에 연결하거나,
  - Supabase Storage에 업로드 후 key(url)를 저장
- 관련 코드 위치:
  - `app/services/storage_service.py`
  - `app/models/media_asset.py`
  - `app/models/attempts.py`

#### D. STT(음성→텍스트) 및 답변 평가
6) **STT 처리**
- `app/routers/answer_stt.py`
- 관련 서비스:
  - `app/services/stt_service.py`
- 결과: 사용자의 답변 텍스트를 생성/저장

7) **답변 평가(내용 평가)**
- `app/routers/answer_eval.py`
- 목적: 답변 텍스트 기반 평가/길이/구성 등의 피드백 생성

#### E. 피드백 분석(음성/표정/자세)
8) **음성 피드백(Voice Feedback)**
- `app/routers/feedback.py` (또는 voice 관련 라우터)
- 내부 동작:
  - 오디오 다운로드/임시파일 생성
  - 음성 분석 수행
  - `FeedbackSummary`에 점수 저장
  - FE용 payload 생성
- 관련 서비스:
  - `app/services/vocal_analysis.py`
  - `app/services/vocal_feedback.py`
  - `app/services/feedback_service.py`

9) **표정 피드백(Expression Feedback)**
- `app/routers/feedback.py` (또는 face 관련 라우터)
- 내부 동작:
  - 영상 프레임 기반 분석
  - 정면 주시율/깜빡임/입꼬리 등 지표 생성
  - `FeedbackSummary` 또는 별도 결과 저장
- 관련 서비스:
  - `app/services/face_analysis.py`

10) **자세 피드백(Pose Feedback)**
- `app/routers/pose_analysis.py`
- 내부 동작:
  - 영상 다운로드/임시파일 생성
  - 포즈 모델 분석 수행(어깨/고개/손 등)
  - `FeedbackSummary`에 점수 및 구간 저장
- 관련 서비스:
  - `app/services/pose_model.py`
  - `app/services/feedback_service.py`

#### F. 결과 통합 조회(프론트 표시)
11) **FeedbackSummary 기반 통합 표시**
- `app/models/feedback_summary.py`
- 목적: attempt별로 음성/표정/자세 점수를 한 화면에서 조회 가능하도록 제공

---
## 3. 실행 환경

- OS: Windows 기준(다른 OS도 가능)
- Python: **3.10.x 권장**
- DB: PostgreSQL (로컬 Docker 또는 Supabase)
- (분석 기능 사용 시) **ffmpeg 설치 필요**
- (선택) Docker 설치 시 DB/배포 환경 구성 쉬움

---

## 4. 로컬 실행 방법

### 4-1) 프로젝트 클론 및 이동
```bash
git clone <YOUR_BACKEND_REPO_URL>
cd interview-be
```
### 4-2) 가상환경 생성 및 활성화(Windows)

```bash
py -3.10 -m venv .venv
.\.venv\Scripts\activate
```
PowerShell에서 실행 정책 때문에 막히면 아래를 한 번 실행한 뒤 다시 활성화하세요.
```bash
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 4-3) 패키지 설치

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4-4) 서버 실행

```bash
python -m uvicorn app.main:app --reload
```
Swagger(OpenAPI): http://127.0.0.1:8000/docs

---

## 5. 환경변수(.env) 설정

레포 루트(`interview-be/.env`)에 `.env` 파일을 생성하세요.

```env
# ===== 필수(서버 기동) =====
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME
SUPABASE_URL=...
SUPABASE_ANON_KEY=...

# (프로젝트에서 JWT를 직접 쓰면 필수)
JWT_SECRET=your_jwt_secret

# ===== 선택(분석 기능) =====
FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe

# ===== 선택(OpenAI) =====
OPENAI_API_KEY=sk-...

# ===== 선택(Google STT) =====
GOOGLE_STT_KEY_PATH=path/to/google-stt-service-account.json

# ===== 선택(Supabase 추가 설정) =====
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWKS_URL=...
SUPABASE_ISSUER=...
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWT_SECRET=...

SUPABASE_STORAGE_URL=...
SUPABASE_VIDEO_BUCKET=videos
SUPABASE_AUDIO_BUCKET=audios

```
.env는 절대 커밋하지 않습니다. (.gitignore에 포함)

---

## 6. DB 준비

프로젝트는 **PostgreSQL**을 사용합니다.  
아래 중 한 가지 방식으로 DB를 준비하세요.

### 6-1) 로컬 Postgres(Docker) 실행(권장)

Docker가 설치되어 있다면 아래 명령으로 로컬 DB를 실행할 수 있습니다.

```bash
docker run --name interview-postgres ^
  -e POSTGRES_USER=postgres ^
  -e POSTGRES_PASSWORD=postgres ^
  -e POSTGRES_DB=interview ^
  -p 5432:5432 -d postgres:15
```
.env 예시 :
```bash
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/interview
JWT_SECRET=dev_secret
```
### 6-2) Supabase(Postgres) 사용(선택)

로컬 DB 대신 **Supabase(PostgreSQL)** 를 사용할 수 있습니다.

1. Supabase에서 프로젝트를 생성합니다.
2. **Database URL**(Postgres 연결 문자열)을 확인합니다.
3. 레포 루트의 `.env`에 `DATABASE_URL`을 설정합니다.

```env
DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME
JWT_SECRET=your_jwt_secret
```
4. (Storage를 쓰는 경우) 아래 항목도 .env에 추가합니다.
```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
VIDEO_BUCKET=your_bucket_name
```
### 6-3) 테이블 생성(create_all) (초기 1회)

Alembic(migration)이 없거나 DB가 비어있는 초기 상태라면 아래 명령을 **1회** 실행해 테이블을 생성합니다.

```bash
python -c "from app.db.session import engine, Base; import app.models.attempts, app.models.sessions, app.models.interviews, app.models.basic_question, app.models.generated_question, app.models.session_question, app.models.media_asset, app.models.records, app.models.user_profile, app.models.feedback_summary; Base.metadata.create_all(bind=engine); print('✅ tables created')"
```
- 실행이 끝나면 ✅ tables created가 출력됩니다.
- 이미 테이블이 존재하면 추가 생성 없이 넘어갈 수 있습니다.

### 6-4) DB 연결 확인(권장)

서버 실행 전에 DB 연결이 되는지 간단히 확인합니다.

```bash
python -c "from app.db.session import SessionLocal; from sqlalchemy import text; db=SessionLocal(); db.execute(text('SELECT 1')); db.close(); print('✅ DB connection ok')"
```

### 6-5) (선택) 기본 데이터(Seed) 주입

프로젝트는 질문 데이터(`BasicQuestion` 등)가 없으면  
세션 시작/질문 선택 기능이 정상 동작하지 않을 수 있습니다.

#### (1) Seed 스크립트가 있는 경우
레포에 seed 스크립트가 있다면 아래처럼 실행하세요.

```bash
python scripts/seed_basic_questions.py
```
#### (2) Seed 스크립트가 없는 경우

README에 아래 내용을 명시하는 것을 권장합니다.

서버 실행 및 /docs 확인은 가능

단, BasicQuestion / GeneratedQuestion 데이터가 없으면
일부 기능(세션 시작, 질문 랜덤 선택 등)이 제한될 수 있음

### 6-6) DB 관련 자주 발생하는 오류 대응(권장)

#### (1) `psycopg2` / 드라이버 오류
```bash
pip install psycopg2-binary
```
#### (2) UndefinedTable (테이블이 없다고 나옴)

- 6-3 테이블 생성(create_all)을 먼저 실행했는지 확인하세요.

- DB URL이 다른 DB를 가리키고 있지 않은지(DATABASE_URL) 확인하세요.

#### (3) 연결 실패(비밀번호/호스트/포트)

- .env의 DATABASE_URL이 올바른지 확인하세요.

- 로컬 Docker DB 사용 시:

  - host: localhost

  - port: 5432

  - db: interview

#### (4) .env를 못 읽는 것 같음

- .env 파일이 레포 루트(interview-be/) 에 있는지 확인하세요.

---

# 7. 실행 확인(필수)
### 7-1) 서버 기동 확인
``` bash
python -m uvicorn app.main:app --reload
```
정상이라면 콘솔에 아래와 유사한 로그가 뜹니다.
- Application startup complete.
- Uvicorn running on http://127.0.0.1:8000
### 7-2) Swagger / OpenAPI 접근 확인
브라우저에서 아래 URL이 열리면 기본 실행은 성공입니다.
- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/openapi.json
### 7-3) (선택) DB 테이블 생성/연결까지 한 번에 확인

DB가 비어있다면 먼저 테이블 생성(6-3)을 1회 수행한 뒤,
서버를 켜고 /docs에서 API 목록이 정상 노출되는지 확인하세요.

---

# 8. Troubleshooting
### 8-1) uvicorn 용어를 찾을 수 없음

가상환경 활성화가 안 됐거나 패키지가 설치 안 된 상태일 가능성이 큽니다.
```bash
# venv 활성화(Windows)
.\.venv\Scripts\activate

# 설치 확인
pip show uvicorn

# 없으면 재설치
pip install -r requirements.txt
```
또는 항상 아래처럼 실행하면 PATH 이슈를 줄일 수 있어요.
```bash
python -m uvicorn app.main:app --reload
```

### 8-2) DB 연결 오류 / UndefinedTable
- .env의 DATABASE_URL이 올바른지 확인
- DB가 비어있다면 6-3(create_all) 을 1회 실행했는지 확인

### 8-3) .env를 못 읽는 것 같음
- .env 파일이 레포 루트(interview-be/) 에 있는지 확인
- (권장) .env 값 바꾼 뒤 서버 완전 재시작

### 8-4) ffmpeg 관련 에러(분석 기능에서 실패)
윈도우라면 .env에 아래 형태 권장(역슬래시 이슈 방지):
```bash
FFMPEG_PATH=C:/ffmpeg/bin/ffmpeg.exe
```
설치 확인:
```bash
ffmpeg -version
```