# Interview Backend (FastAPI)
이 문서는 면접 세션 중 발생하는 미디어 저장, 자세 분석 실행, 분석 결과 조회 기능을 담당하는 백엔드 모듈에 대한 설명입니다.
본 백엔드는 FastAPI 기반으로 작성되며, Supabase Storage + Function 기반 구조를 사용합니다.

## 📁 프로젝트 구조
app/
│ .env
│ api_deps.py
│ config.py
│ main.py
│ README.md
│
├─api
│ pose_analysis.py
│ sessions.py
│ init.py
│
├─db
│ models.py
│ session.py
│ init.py
│
└─services
feedback_service.py
pose_model.py
init.py


API 엔드포인트
1. 세션 관련
- POST /api/interviews/{interview_id}/sessions/start
    -인터뷰 시작, 세션/질문/attempt 생성
    -반환: session_id, question_id, attempt_id

2. 포즈 분석
- POST /api/analysis/pose/start
    - Background Task로 비디오 분석 시작
    - 요청: session_id, attempt_id
    - 반환: 분석 시작 상태 (202 Accepted)
- GET /api/feedback/{session_id}/pose-feedback
    -분석 결과 조회
    -반환: 점수(overall_score), 카테고리 점수, 문제 구간(JSON)

DB 모델
- 주요 테이블:
    -users: 사용자
    -content: 인터뷰 콘텐츠
    -sessions: 세션 정보
    -session_question: 세션별 질문
    -attempts: 질문 응답 시도
    -media_asset: 업로드된 비디오/오디오/이미지
    -feedback_summary: 포즈/얼굴/음성 등 피드백

포즈 분석 로직
- MediaPipe Pose 사용하여 keypoints 추출
- 어깨, 고개, 손 위치 계산
- 점수(score) 계산 후 등급(rating) 변환
- 문제 구간(problem_sections)을 JSON으로 저장
- FeedbackSummary에 생성/업데이트

참고
- 현재 유저 인증은 stub 형태이며, 실제 프로젝트에서는 Supabase JWT 검증으로 대체 필요.
- Background Task로 처리되므로, 분석 완료까지 약간의 시간이 소요될 수 있음.