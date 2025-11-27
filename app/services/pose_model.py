# app/services/pose_model.py
import cv2
import pandas as pd
import numpy as np
import mediapipe as mp
import tempfile
import requests
import os

def run_pose_on_video(video_path: str):
    """
    video_path: 로컬 경로 or 외부 URL (Storage URL)
    반환값: feedback_json (dict)
    """
    # -----------------
    # 1️⃣ 로컬/URL 처리
    # -----------------
    tmp_file_path = None
    if video_path.startswith("http"):
        # URL이면 임시 파일로 다운로드
        tmp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_file_path = tmp_file.name
        r = requests.get(video_path, stream=True)
        if r.status_code != 200:
            raise ValueError(f"Cannot download video: {video_path}")
        for chunk in r.iter_content(chunk_size=8192):
            tmp_file.write(chunk)
        tmp_file.close()
        video_path_local = tmp_file_path
    else:
        video_path_local = video_path

    # -----------------
    # 2️⃣ MediaPipe 초기화
    # -----------------
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5
    )

    cap = cv2.VideoCapture(video_path_local)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path_local}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    keypoints_list = []
    frame_idx = 0

    while True:
        success, frame = cap.read()
        if not success:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            kp = {"frame": frame_idx}
            for i, lm in enumerate(landmarks):
                kp[f"x_{i}"] = lm.x
                kp[f"y_{i}"] = lm.y
                kp[f"z_{i}"] = lm.z
                kp[f"v_{i}"] = lm.visibility
            keypoints_list.append(kp)
        frame_idx += 1

    cap.release()

    # -----------------
    # 3️⃣ 자세 분석
    # -----------------
    df_key = pd.DataFrame(keypoints_list)

    def analyze_posture(df):
        VIS_THRESHOLD = 0.5
        k = 5
        problem_frames = []
        feedback_records = []
        shoulder_bad, head_bad, hand_bad = [], [], []

        def score_from_diff(diff, th):
            return 1.0 if diff <= th else max(1 - (diff - th) * k, 0)

        for _, row in df.iterrows():
            def get_part(idx):
                return (row[f"x_{idx}"], row[f"y_{idx}"]) if row[f"v_{idx}"] >= VIS_THRESHOLD else None

            L_sh, R_sh = get_part(11), get_part(12)
            Nose = get_part(0)
            L_hand, R_hand = get_part(16), get_part(15)

            # 어깨
            diff_sh = abs(L_sh[1] - R_sh[1]) if (L_sh and R_sh) else 0.04399
            shoulder_score = score_from_diff(diff_sh, 0.04399)
            if shoulder_score < 0.9:
                shoulder_bad.append(int(row["frame"]))

            # 고개
            if Nose and L_sh and R_sh:
                mid_x = (L_sh[0] + R_sh[0]) / 2
                diff_head = abs(Nose[0] - mid_x)
            else:
                diff_head = 0.01017
            head_score = score_from_diff(diff_head, 0.01017)
            if head_score < 0.9:
                head_bad.append(int(row["frame"]))

            # 손
            hand_score = 1.0
            if L_hand and R_hand and L_sh and R_sh:
                diff_hand = max(L_sh[1] - L_hand[1], R_sh[1] - R_hand[1])
                if diff_hand > 0:
                    hand_score = max(1 - diff_hand * k, 0)
            if hand_score < 0.9:
                hand_bad.append(int(row["frame"]))

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
            start = prev = frames[0]
            for f in frames[1:]:
                if f == prev + 1:
                    prev = f
                else:
                    sections.append((start, prev))
                    start = prev = f
            sections.append((start, prev))
            return sections

        df_out = pd.DataFrame(feedback_records)
        return df_out, (merge(shoulder_bad), merge(head_bad), merge(hand_bad))

    df_feedback, problem_sections = analyze_posture(df_key)

    # -----------------
    # 4️⃣ JSON 생성
    # -----------------
    def generate_feedback_json(df, problem_sections):
        alerts = []
        advice_map = {
            "shoulder": "{side} 어깨가 올라갔습니다.",
            "head_tilt": "고개가 {side}로 기울어 있습니다.",
            "hand": "손은 어깨 아래 위치로 유지해주세요."
        }

        for col in ["shoulder", "head_tilt", "hand"]:
            if col == "shoulder":
                diff_col = "shoulder_diff"
                threshold = 0.04399
            elif col == "head_tilt":
                diff_col = "head_diff"
                threshold = 0.01017
            else:
                diff_col = None

            if col in ["shoulder", "head_tilt"]:
                idxs = df.index[df[diff_col].abs() > threshold].tolist()
            else:
                idxs = df.index[df["hand"] < 1.0].tolist()
            if not idxs:
                continue

            group_ids = (pd.Series(idxs).diff() > 1).cumsum()
            grouped = pd.DataFrame({"frame": idxs, "group": group_ids})
            for g_id, g_frames in grouped.groupby("group"):
                start_f = g_frames.frame.min()
                end_f = g_frames.frame.max()
                if (end_f - start_f)/fps < 1.0:
                    continue
                if col == "shoulder":
                    side = "왼쪽" if df.loc[start_f:end_f, "shoulder_diff"].mean() > 0 else "오른쪽"
                    msg = advice_map[col].format(side=side)
                elif col == "head_tilt":
                    side = "왼쪽" if df.loc[start_f:end_f, "head_diff"].mean() > 0 else "오른쪽"
                    msg = advice_map[col].format(side=side)
                else:
                    msg = advice_map[col]
                alerts.append({"start_time": start_f/fps, "end_time": end_f/fps, "issue": col, "message": msg})

        overall_score = np.mean([df['shoulder'].mean()*100, df['head_tilt'].mean()*100, df['hand'].mean()*100])
        return {
            "feedback_timeline": alerts,
            "problem_sections": {
                "shoulder": [[s/fps, e/fps] for s,e in problem_sections[0]],
                "head_tilt": [[s/fps, e/fps] for s,e in problem_sections[1]],
                "hand": [[s/fps, e/fps] for s,e in problem_sections[2]]
            },
            "overall_score": round(overall_score,2),
            "posture_score": {
                "shoulder": round(df['shoulder'].mean()*100,2),
                "head_tilt": round(df['head_tilt'].mean()*100,2),
                "hand": round(df['hand'].mean()*100,2)
            }
        }

    feedback_json = generate_feedback_json(df_feedback, problem_sections)

    # -----------------
    # 5️⃣ 임시 파일 삭제
    # -----------------
    if tmp_file_path and os.path.exists(tmp_file_path):
        os.remove(tmp_file_path)

    return feedback_json
