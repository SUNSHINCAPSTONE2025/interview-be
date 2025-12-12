# app/services/feedback_service.py
from app.models.feedback_summary import FeedbackSummary
from sqlalchemy import func
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

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

def create_or_update_pose_feedback(db, session_id: int, attempt_id: int, pose_json: dict):
    """
    pose_json: generate_feedback_json() 결과
    DB의 feedback_summary.session_id에 생성 또는 업데이트
    """
    fs = get_or_create_feedback_summary(db, session_id, attempt_id)

    fs.overall_pose = pose_json.get("overall_score")
    fs.shoulder = pose_json.get("category_scores", {}).get("shoulder", {}).get("value")
    fs.head = pose_json.get("category_scores", {}).get("head_tilt", {}).get("value")
    fs.hand = pose_json.get("category_scores", {}).get("hand", {}).get("value")

    db.add(fs)
    db.commit()
    return fs

def create_or_update_voice_feedback(db, session_id: int, attempt_id: int, voice_json: dict) -> FeedbackSummary:
    fs = get_or_create_feedback_summary(db, session_id, attempt_id)

    fs.overall_voice = voice_json.get("total_score")

    metrics = {m["id"]: m for m in voice_json.get("metrics", [])}

    tremor_m = metrics.get("tremor")
    if tremor_m:
        fs.tremor = tremor_m.get("score")

    pause_m = metrics.get("pause")
    if pause_m:
        fs.blank = pause_m.get("score")

    tone_m = metrics.get("tone")
    if tone_m:
        fs.tone = tone_m.get("score")

    speed_m = metrics.get("speed")
    if speed_m:
        fs.speed = speed_m.get("score")

    # 음성 한줄 요약은 DB에 저장하지 않음 (API 응답에서만 반환)
    # comment 필드는 답변 평가(LLM)용으로만 사용

    db.add(fs)
    db.commit()
    db.refresh(fs)
    return fs


def build_voice_payload_from_summary(fs: FeedbackSummary) -> dict:
    """
    GET /api/sessions/{id}/voice-feedback 응답용 간단 payload 생성.
    comment 필드는 답변 평가(LLM)용이므로 음성 피드백에서는 사용하지 않음.
    """
    total = fs.overall_voice or fs.overall or 0.0

    return {
        "total_score": int(round(total)),
        "summary": "",  # 음성 요약은 DB에 저장하지 않으므로 빈 문자열
        "metrics": [
            {
                "id": "tremor",
                "label": "떨림",
                "score": fs.tremor,
            },
            {
                "id": "pause",
                "label": "공백",
                "score": fs.blank,
            },
            {
                "id": "tone",
                "label": "억양",
                "score": fs.tone,
            },
            {
                "id": "speed",
                "label": "속도",
                "score": fs.speed,
            },
        ],
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