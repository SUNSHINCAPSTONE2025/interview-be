# 프리뷰/세션 시작에 대한 레이트리밋과 동시 세션 방지(중복 시작 409)를 담당하는 in-memory 헬퍼.
import time
import uuid
from collections import defaultdict

# ---- 설정(원하면 .env로 빼도 됨) ----
PREVIEW_LIMIT = 20          # 프리뷰 허용 횟수
PREVIEW_WINDOW_SEC = 60     # 초
GENERATE_LIMIT = 10         # 세션 시작/질문 생성 허용 횟수
GENERATE_WINDOW_SEC = 60    # 초
ESTIMATED_DURATION_MIN = 15 # 202 Accepted 응답에 표시

# 레이트리밋 카운터
_preview_hits = defaultdict(list)     # key: user_id
_generate_hits = defaultdict(list)    # key: user_id

# 인터뷰별 동시 실행 방지(간단한 락)
_running_by_interview = set()         # {interview_id}

def _prune(bucket, window):
    now = time.time()
    return [t for t in bucket if now - t < window]

def check_preview_rate(user_id: int) -> None:
    _preview_hits[user_id] = _prune(_preview_hits[user_id], PREVIEW_WINDOW_SEC)
    if len(_preview_hits[user_id]) >= PREVIEW_LIMIT:
        raise RuntimeError("rate_limited_preview")
    _preview_hits[user_id].append(time.time())

def check_generate_rate(user_id: int) -> None:
    _generate_hits[user_id] = _prune(_generate_hits[user_id], GENERATE_WINDOW_SEC)
    if len(_generate_hits[user_id]) >= GENERATE_LIMIT:
        raise RuntimeError("rate_limited_generate")
    _generate_hits[user_id].append(time.time())

def is_running(interview_id: int) -> bool:
    return interview_id in _running_by_interview

def mark_running(interview_id: int) -> None:
    _running_by_interview.add(interview_id)

def unmark_running(interview_id: int) -> None:
    _running_by_interview.discard(interview_id)

def new_ids():
    return f"sess_{uuid.uuid4().hex[:6]}", f"gen_{uuid.uuid4().hex[:5]}"

def estimated_minutes() -> int:
    return ESTIMATED_DURATION_MIN
