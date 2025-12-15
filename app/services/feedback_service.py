# app/services/feedback_service.py
from app.models.feedback_summary import FeedbackSummary
from sqlalchemy import func
import numpy as np
import pandas as pd
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

def _to_float(value):
    """numpy / str / dict(value 포함) -> float 로 안전 변환"""
    if value is None:
        return None

    if isinstance(value, dict):
        value = value.get("value")

    if value is None:
        return None

    if isinstance(value, np.generic):
        return value.item()

    try:
        return float(value)
    except (TypeError, ValueError):
        return None

# (1) 포즈 피드백 관련 함수

def generate_feedback_json(df, problem_sections, fps=30, min_duration=1.0,
                           th_sh=0.04399, th_head=0.01017):
    advice_map = {
        "shoulder": "{side} 어깨가 올라갔습니다. 양 어깨를 수평으로 맞추어주세요.",
        "head_tilt": "고개가 {side}로 기울어 있습니다. 천천히 중앙으로 맞춰주세요.",
        "hand": "손은 어깨 아래 위치로 유지해주세요."
    }

    alerts = []

    for col in ["shoulder", "head_tilt", "hand"]:
        if col == "shoulder":
            diff_col = "shoulder_diff"
            threshold = th_sh
        elif col == "head_tilt":
            diff_col = "head_diff"
            threshold = th_head
        else:
            diff_col = None

        if col in ["shoulder", "head_tilt"]:
            problem_idx = df.index[df[diff_col].abs() > threshold].tolist()
        else:
            problem_idx = df.index[df["hand"] < 1.0].tolist()

        if not problem_idx:
            continue

        group_ids = (pd.Series(problem_idx).diff() > 1).cumsum()
        grouped = pd.DataFrame({"frame": problem_idx, "group": group_ids})

        for g_id, g_frames in grouped.groupby("group"):
            start_f = g_frames['frame'].min()
            end_f = g_frames['frame'].max()
            duration = (end_f - start_f) / fps
            if duration < min_duration:
                continue

            if col == "shoulder":
                mean_diff = df.loc[start_f:end_f, "shoulder_diff"].mean()
                side = "왼쪽" if mean_diff > 0 else "오른쪽"
                message = advice_map[col].format(side=side)
            elif col == "head_tilt":
                mean_diff = df.loc[start_f:end_f, "head_diff"].mean()
                side = "왼쪽" if mean_diff > 0 else "오른쪽"
                message = advice_map[col].format(side=side)
            else:
                message = advice_map[col]

            alerts.append({
                "start_time": round(start_f / fps, 2),
                "end_time": round(end_f / fps, 2),
                "issue": col,
                "message": message
            })

    def get_rating(score):
        if score >= 90:
            return "양호"
        elif score >= 70:
            return "보통"
        else:
            return "미흡"

    avg_shoulder = df['shoulder'].mean() * 100
    avg_head = df['head_tilt'].mean() * 100
    avg_hand = df['hand'].mean() * 100
    overall_score = np.mean([avg_shoulder, avg_head, avg_hand])

    overall_rating = get_rating(overall_score)
    category_ratings = {
        "shoulder": get_rating(avg_shoulder),
        "head_tilt": get_rating(avg_head),
        "hand": get_rating(avg_hand)
    }

    json_data = {
        "feedback_timeline": alerts,
        "problem_sections": {
            "shoulder": [[round(s/fps,2), round(e/fps,2)] for s, e in problem_sections[0]],
            "head_tilt": [[round(s/fps,2), round(e/fps,2)] for s, e in problem_sections[1]],
            "hand": [[round(s/fps,2), round(e/fps,2)] for s, e in problem_sections[2]]
        },
        "overall_score": round(overall_score, 2),
        "overall_rating": overall_rating,
        "category_scores": {
            "shoulder": {"value": round(avg_shoulder,2), "rating": category_ratings["shoulder"]},
            "head_tilt": {"value": round(avg_head,2), "rating": category_ratings["head_tilt"]},
            "hand": {"value": round(avg_hand,2), "rating": category_ratings["hand"]}
        }
    }

    return json_data

# (2) 공통 FeedbackSummary 헬퍼
def get_or_create_feedback_summary(db, session_id: int, attempt_id: int,) -> FeedbackSummary:
    fs = db.query(FeedbackSummary).filter(
        FeedbackSummary.session_id == session_id,
        FeedbackSummary.attempt_id == attempt_id
    ).first()
    if not fs:
        fs = FeedbackSummary(
            session_id=session_id,
            attempt_id=attempt_id,
        )
        db.add(fs)
        db.flush()  # PK 채우기

    return fs

def create_or_update_pose_feedback(
    db: Session,
    session_id: int,
    attempt_id: int,
    pose_json: Dict[str, Any],
) -> FeedbackSummary:
    """
    pose_json: generate_feedback_json() 결과
    DB의 feedback_summary.session_id에 생성 또는 업데이트
    """
    fs = get_or_create_feedback_summary(db, session_id, attempt_id)

    # 전체 포즈 점수 (0~100)
    total_score_raw = pose_json.get("overall_score")
    fs.overall_pose = _to_float(total_score_raw)

    # 카테고리별 점수 (0~100)
    category_scores = pose_json.get("category_scores", {}) or {}

    fs.shoulder = _to_float(category_scores.get("shoulder"))
    fs.head = _to_float(category_scores.get("head_tilt"))
    fs.hand = _to_float(category_scores.get("hand"))

    # 문제 구간(problem_sections)도 함께 저장
    # FeedbackSummary.problem_sections 가 JSONB 컬럼이라고 가정
    problem_sections = pose_json.get("problem_sections", {})
    try:
        # 이미 리스트/딕셔너리면 그대로 저장해도 되고,
        # DB가 JSONB면 SQLAlchemy가 알아서 직렬화해 줌
        fs.problem_sections = problem_sections
    except Exception:
        # 혹시 타입 문제를 피하려고 방어적으로 한 번 더 처리
        fs.problem_sections = json.loads(
            json.dumps(problem_sections, ensure_ascii=False)
        )

    db.add(fs)
    db.commit()
    db.refresh(fs)
    return fs

def create_or_update_voice_feedback(
    db: Session,
    session_id: int,
    attempt_id: int,
    voice_json: Dict[str, Any],
    ) -> FeedbackSummary:
    """
    음성 분석 결과를 FeedbackSummary 테이블에 저장/업데이트

    voice_json 구조 예시:
    {
        "total_score": 82.5,
        "metrics": [
            {"id": "tremor", "label": "...", "score": 90.0},
            {"id": "pause",  "label": "...", "score": 65.0},
            {"id": "tone",   "label": "...", "score": 70.0},
            {"id": "speed",  "label": "...", "score": 78.0},
        ],
        "summary": "..."   # ← 이건 DB에 저장하지 않음
    }
    """
    fs = get_or_create_feedback_summary(db, session_id, attempt_id)

    # 전체 점수 (0~100)
    total_score_raw = voice_json.get("total_score", 0)
    fs.overall_voice = _to_float(total_score_raw)

    metrics: List[Dict[str, Any]] = voice_json.get("metrics", []) or []
    metric_map: Dict[str, Dict[str, Any]] = {m.get("id"): m for m in metrics}

    # tremor
    tremor_m = metric_map.get("tremor")
    if tremor_m is not None:
        fs.tremor = _to_float(tremor_m.get("score"))

    # pause(머뭇거림) → DB 컬럼명은 blank
    pause_m = metric_map.get("pause")
    if pause_m is not None:
        fs.blank = _to_float(pause_m.get("score"))

    # tone
    tone_m = metric_map.get("tone")
    if tone_m is not None:
        fs.tone = _to_float(tone_m.get("score"))

    # speed
    speed_m = metric_map.get("speed")
    if speed_m is not None:
        fs.speed = _to_float(speed_m.get("score"))

    # summary(한 줄 요약)는 DB에 저장하지 않고,
    # build_voice_payload_from_summary에서 점수 기반으로 다시 생성

    db.add(fs)
    db.commit()
    db.refresh(fs)
    return fs


def build_voice_payload_from_summary(fs: FeedbackSummary) -> Dict[str, Any]:
    """
    FeedbackSummary에 저장된 음성 지표를 기반으로
    FE에서 바로 쓸 수 있는 payload 형식으로 변환.

    - total_score: 0~100
    - summary: 떨림/머뭇거림/억양/속도까지 포함한 한 줄~두 줄 요약
    - metrics: FE 그래프용 개별 지표
    """
    # 안전하게 float로 변환
    total = _to_float(fs.overall_voice) or 0.0

    tremor_val = _to_float(fs.tremor)
    pause_val = _to_float(fs.blank)
    tone_val = _to_float(fs.tone)
    speed_val = _to_float(fs.speed)

    # 개별 메트릭 리스트 (FE에서 그대로 쓰던 구조 유지)
    metrics: List[Dict[str, Any]] = [
        {"id": "tremor", "label": "떨림", "score": tremor_val},
        {"id": "pause", "label": "머뭇거림", "score": pause_val},
        {"id": "tone", "label": "억양", "score": tone_val},
        {"id": "speed", "label": "속도", "score": speed_val},
    ]

    # ----- summary 생성 로직 -----
    # 기준: 0~100 점수를 3단계(좋음/보통/주의)로 나눠서 문장 조합
    def level(v: Optional[float]) -> Optional[str]:
        if v is None:
            return None
        if v >= 80:
            return "good"
        if v >= 60:
            return "okay"
        return "bad"

    overall_lv = level(total)

    if overall_lv == "good":
        first_sentence = "전체적으로 안정적인 음성이었습니다."
    elif overall_lv == "okay":
        first_sentence = "전체적으로 무난한 음성이었지만, 몇 가지 개선할 부분이 보입니다."
    else:
        first_sentence = "전체적으로 개선이 필요한 음성이었습니다."

    detail_sentences: List[str] = []

    # 떨림
    tremor_lv = level(tremor_val)
    if tremor_lv == "good":
        detail_sentences.append("목소리 떨림 없이 비교적 안정적으로 말했습니다.")
    elif tremor_lv == "okay":
        detail_sentences.append("약간의 떨림이 느껴지지만 전체 흐름에 큰 문제는 없습니다.")
    elif tremor_lv == "bad":
        detail_sentences.append("긴장으로 인한 목소리 떨림이 자주 느껴졌습니다.")

    # 머뭇거림(pause)
    pause_lv = level(pause_val)
    if pause_lv == "good":
        detail_sentences.append("머뭇거림이 거의 없어 답변 흐름이 자연스러웠습니다.")
    elif pause_lv == "okay":
        detail_sentences.append("생각을 정리하는 짧은 머뭇거림이 있었지만 전반적으로 무난했습니다.")
    elif pause_lv == "bad":
        detail_sentences.append("답변 중 머뭇거림이 길거나 자주 나타나 핵심 메시지가 약해질 수 있습니다.")

    # 억양(tone)
    tone_lv = level(tone_val)
    if tone_lv == "good":
        detail_sentences.append("억양이 자연스럽고 전달력이 좋았습니다.")
    elif tone_lv == "okay":
        detail_sentences.append("전반적으로 자연스러운 억양이지만 약간 단조로운 구간이 있습니다.")
    elif tone_lv == "bad":
        detail_sentences.append("억양이 다소 단조로운 편이라, 문장 끝을 더 분명하게 처리해 주면 좋습니다.")

    # 속도(speed)
    speed_lv = level(speed_val)
    if speed_lv == "good":
        detail_sentences.append("말 속도가 적절해 듣기 편했습니다.")
    elif speed_lv == "okay":
        detail_sentences.append("약간 빠르거나 느린 구간이 있지만 전체적으로는 무난한 속도였습니다.")
    elif speed_lv == "bad":
        detail_sentences.append("말 속도가 다소 빠르거나 느려 전달력이 떨어질 수 있습니다.")

    # 문장 합치기
    summary_parts = [first_sentence]
    if detail_sentences:
        # 너무 길어지지 않게 앞에서 2~3개 정도만 사용하고 싶으면 슬라이싱해서 줄여도 됨
        summary_parts.append(" ".join(detail_sentences))

    summary = " ".join(summary_parts)

    return {
        "total_score": int(round(total)),
        "summary": summary,
        "metrics": metrics,
    }


def create_or_update_comment_feedback(
    db: Session,
    session_id: int,
    attempt_id: int,
    comment: str,
) -> FeedbackSummary:
    
    fs = (
        db.query(FeedbackSummary)
        .filter(
            FeedbackSummary.session_id == session_id,
            FeedbackSummary.attempt_id == attempt_id,
        )
        .first()
    )

    if fs is None:
        fs = FeedbackSummary(
            session_id=session_id,
            attempt_id=attempt_id,
        )
        db.add(fs)

    fs.comment = comment

    db.commit()
    db.refresh(fs)
    return fs