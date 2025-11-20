# -*- coding: utf-8 -*-
# =====================================
# 1️⃣ 라이브러리 설치
# =====================================
!pip install mediapipe opencv-python numpy pandas moviepy

# =====================================
# 2️⃣ 영상 업로드
# =====================================
from google.colab import files
uploaded = files.upload()
video_path = list(uploaded.keys())[0]
print(f"✅ 업로드 완료: {video_path}")

import mediapipe as mp
import cv2
import pandas as pd
import numpy as np
import json

# =====================================
# 3️⃣ MediaPipe로 키포인트 추출
# =====================================
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=False,
                    model_complexity=1,
                    enable_segmentation=False,
                    min_detection_confidence=0.5)

cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS)
keypoints_list = []
frame_idx = 0

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose.process(frame_rgb)

    if results.pose_landmarks:
        landmarks = results.pose_landmarks.landmark
        keypoints = {'frame': frame_idx}
        for i, lm in enumerate(landmarks):
            keypoints[f'x_{i}'] = lm.x
            keypoints[f'y_{i}'] = lm.y
            keypoints[f'z_{i}'] = lm.z
            keypoints[f'v_{i}'] = lm.visibility
        keypoints_list.append(keypoints)

    frame_idx += 1

cap.release()

df_key = pd.DataFrame(keypoints_list)
df_key.to_csv("/content/pose_keypoints.csv", index=False)
print(f"✅ 좌표 추출 완료 ({len(df_key)} 프레임, FPS={fps:.1f})")

# =====================================
# 4️⃣ 자세 평가 + 문제 구간/점수 계산
# =====================================
def analyze_posture_fixed(csv_path, th_sh=0.04399, th_head=0.01017):
    df = pd.read_csv(csv_path)
    VIS_THRESHOLD = 0.5
    k = 5  # 감점 민감도
    frame_duration = 1.0 / fps

    problem_frames = []
    feedback_records = []
    shoulder_bad, head_bad, hand_bad = [], [], []

    def score_from_diff(diff, th):
        return 1.0 if diff <= th else max(1 - (diff - th) * k, 0)

    for _, row in df.iterrows():
        def get_part(idx):
            return (row[f'x_{idx}'], row[f'y_{idx}']) if row[f'v_{idx}'] >= VIS_THRESHOLD else None

        L_sh, R_sh = get_part(11), get_part(12)
        Nose = get_part(0)
        L_hand, R_hand = get_part(16), get_part(15)

        # 어깨
        diff_sh = abs(L_sh[1] - R_sh[1]) if (L_sh and R_sh) else th_sh
        shoulder_score = score_from_diff(diff_sh, th_sh)
        if shoulder_score < 0.9: shoulder_bad.append(int(row["frame"]))

        # 고개
        if Nose and L_sh and R_sh:
            shoulder_mid_x = (L_sh[0] + R_sh[0]) / 2
            diff_head = abs(Nose[0] - shoulder_mid_x)
        else:
            diff_head = th_head
        head_score = score_from_diff(diff_head, th_head)
        if head_score < 0.9: head_bad.append(int(row["frame"]))

        # 손
        diff_hand = 0
        hand_score = 1.0
        if L_hand and R_hand and L_sh and R_sh:
            diff_hand = max(L_sh[1] - L_hand[1], R_sh[1] - R_hand[1])
            if diff_hand > 0:
                hand_score = max(1 - diff_hand * k, 0)
        if hand_score < 0.9: hand_bad.append(int(row["frame"]))

        avg_score = np.mean([shoulder_score, head_score, hand_score])
        feedback_records.append({
            "frame": int(row["frame"]),
            "shoulder": shoulder_score,
            "head_tilt": head_score,
            "hand": hand_score,
            "avg_score": avg_score,
            "shoulder_diff": diff_sh,
            "head_diff": diff_head
        })

        if avg_score < 0.9:
            problem_frames.append(int(row["frame"]))

    def merge(frames):
        sections = []
        if not frames:
            return sections
        start = frames[0]
        prev = start
        for f in frames[1:]:
            if f == prev + 1:
                prev = f
            else:
                sections.append((start, prev))
                start = f
                prev = f
        sections.append((start, prev))
        return [(s, e) for s, e in sections if (e - s + 1) * frame_duration >= 0.5]

    shoulder_sections = merge(shoulder_bad)
    head_sections = merge(head_bad)
    hand_sections = merge(hand_bad)

    df_out = pd.DataFrame(feedback_records)
    df_out.to_csv("/content/pose_feedback.csv", index=False)

    return df_out, (shoulder_sections, head_sections, hand_sections)

# =====================================
# 5️⃣ 전체 평가 + JSON 생성
# =====================================
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

        # 문제 프레임 탐지
        if col in ["shoulder", "head_tilt"]:
            problem_idx = df.index[df[diff_col].abs() > threshold].tolist()
        else:
            problem_idx = df.index[df["hand"] < 1.0].tolist()

        if not problem_idx:
            continue

        # 연속 구간 묶기
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

    # ========================
    # 전체 점수 및 등급 계산
    # ========================
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

    with open("/content/feedback.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    return json_data

# =====================================
# ✅ 실행
# =====================================
feedback_df, problem_sections = analyze_posture_fixed("/content/pose_keypoints.csv")
feedback_json = generate_feedback_json(feedback_df, problem_sections)

# 예시 출력
#print(json.dumps(feedback_json, ensure_ascii=False, indent=2))
