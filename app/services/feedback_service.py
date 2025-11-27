# app/services/feedback_service.py
from app.models.feedback_summary import FeedbackSummary
from sqlalchemy import func
import numpy as np
import pandas as pd

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


def create_or_update_pose_feedback(db, session_id: int, pose_json: dict):
    """
    pose_json: generate_feedback_json() 결과
    DB의 feedback_summary.session_id에 생성 또는 업데이트
    """
    fs = db.query(FeedbackSummary).filter(FeedbackSummary.session_id == session_id).first()
    if fs is None:
        fs = FeedbackSummary(session_id=session_id)

    fs.overall_pose = pose_json.get("overall_score")
    fs.shoulder = pose_json.get("category_scores", {}).get("shoulder", {}).get("value")
    fs.head = pose_json.get("category_scores", {}).get("head_tilt", {}).get("value")
    fs.hand = pose_json.get("category_scores", {}).get("hand", {}).get("value")
    fs.problem_sections = pose_json.get("problem_sections")
    fs.created_at = func.now()  # datetime.utcnow() → DB에서 현재 시각 자동 기록

    db.add(fs)
    db.commit()
    return fs