from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List, Tuple, Dict, Optional
import os, math, time
import numpy as np
import cv2
import mediapipe as mp


# 설정
GAZE_OFF_ABS = 0.12         
EYE_OFF_ABS  = 0.35         
BLINK_RATIO = 0.75          
BLINK_MIN_DUR = 0.08        
EMA_ALPHA = 0.25           
MOUTH_DELTA = 0.02          

# FaceMesh 세팅
mp_face_mesh = mp.solutions.face_mesh
FACE_MESH = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

# 랜드마크 인덱스
LEFT_EYE  = [33,160,158,133,153,144]
RIGHT_EYE = [263,387,385,362,380,373]
LEFT_EYE_CORNERS  = (33, 133)
RIGHT_EYE_CORNERS = (263, 362)
LEFT_EYE_LIDS     = (159, 145)
RIGHT_EYE_LIDS    = (386, 374)
LEFT_IRIS_IDXS  = [474, 475, 476, 477]
RIGHT_IRIS_IDXS = [469, 470, 471, 472]

MOUTH_LEFT_CORNER  = 61
MOUTH_RIGHT_CORNER = 291
MOUTH_UPPER_INNER  = 13
MOUTH_LOWER_INNER  = 14
NOSE_TIP = 1


# 유틸/지표 계산
def norm_pt(lm, w, h):
    return np.array([lm.x * w, lm.y * h, lm.z], dtype=np.float32)

def head_pose_proxy(lms, w, h):
    nose = norm_pt(lms[NOSE_TIP], w, h)
    cx, cy = w/2.0, h/2.0
    return float((nose[0]-cx)/w), float((nose[1]-cy)/h)  # (yaw, pitch 대용)

def ear_from_landmarks(lms, w, h, idxs):
    pts = [norm_pt(lms[i], w, h) for i in idxs]
    p1, p2, p3, p4, p5, p6 = pts
    dv1 = np.linalg.norm(p2[:2] - p6[:2])
    dv2 = np.linalg.norm(p3[:2] - p5[:2])
    dh  = np.linalg.norm(p1[:2] - p4[:2])
    if dh == 0: return 0.0
    return float((dv1 + dv2) / (2.0*dh))

def mouth_corners_relative(lms, w, h):
    left  = norm_pt(lms[MOUTH_LEFT_CORNER],  w, h)
    right = norm_pt(lms[MOUTH_RIGHT_CORNER], w, h)
    up_in = norm_pt(lms[MOUTH_UPPER_INNER],  w, h)
    lo_in = norm_pt(lms[MOUTH_LOWER_INNER],  w, h)
    center = (up_in + lo_in) / 2.0
    rel_left  = (left[1]  - center[1]) / h
    rel_right = (right[1] - center[1]) / h
    return float((rel_left + rel_right) / 2.0)

def iris_centers_from_landmarks(lms, w, h):
    L = [norm_pt(lms[i], w, h) for i in LEFT_IRIS_IDXS  if i < len(lms)]
    R = [norm_pt(lms[i], w, h) for i in RIGHT_IRIS_IDXS if i < len(lms)]
    lc = np.mean(np.array(L), axis=0) if len(L) >= 3 else None
    rc = np.mean(np.array(R), axis=0) if len(R) >= 3 else None
    return lc, rc

def eye_local_axes(lms, w, h, corners, lids):
    c_out = norm_pt(lms[corners[0]], w, h)
    c_in  = norm_pt(lms[corners[1]], w, h)
    e_center = (c_out + c_in) / 2.0
    ex = c_in[:2] - c_out[:2]
    exn = ex / (np.linalg.norm(ex) + 1e-6)
    lid_up  = norm_pt(lms[lids[0]], w, h)
    lid_dn  = norm_pt(lms[lids[1]], w, h)
    ey = lid_dn[:2] - lid_up[:2]
    eyn = ey / (np.linalg.norm(ey) + 1e-6)
    w_eye = np.linalg.norm(ex)
    h_eye = np.linalg.norm(ey)
    return e_center, exn, eyn, w_eye, h_eye

def eye_gaze_offset(lms, w, h, iris_center, corners, lids):
    if iris_center is None:
        return None
    e_center, ex, ey, w_eye, h_eye = eye_local_axes(lms, w, h, corners, lids)
    d = iris_center[:2] - e_center[:2]
    hor = float(np.dot(d, ex) / (w_eye + 1e-6))
    ver = float(np.dot(d, ey) / (h_eye + 1e-6))
    return hor, ver

def ema_update(prev, new, alpha=EMA_ALPHA):
    if prev is None: return new
    return (1 - alpha) * prev + alpha * new

def compute_fixation_metrics(xs: List[float], ys: List[float], target=(0.0, 0.0)):
    if not xs or not ys or len(xs) != len(ys):
        return {"MAE": None, "SDx": None, "SDy": None, "rho": None, "BCEA": None, "S2S": None}
    X = np.array(xs, dtype=np.float32)
    Y = np.array(ys, dtype=np.float32)
    tx, ty = target
    MAE = float(np.mean(np.sqrt((X - tx)**2 + (Y - ty)**2)))
    SDx = float(np.std(X, ddof=0))
    SDy = float(np.std(Y, ddof=0))
    if len(X) > 1:
        rho = float(np.corrcoef(X, Y)[0, 1])
        if np.isnan(rho): rho = 0.0
    else:
        rho = 0.0
    k = 1.14
    base = max(0.0, 1.0 - rho**2)
    BCEA = float(2 * k * SDx * SDy * math.sqrt(base))
    if len(X) > 1:
        diffs = np.sqrt(np.diff(X)**2 + np.diff(Y)**2)
        S2S = float(np.sqrt(np.mean(diffs**2)))
    else:
        S2S = None
    return {"MAE": MAE, "SDx": SDx, "SDy": SDy, "rho": rho, "BCEA": BCEA, "S2S": S2S}

def safe_num(x: Optional[float]) -> Optional[float]:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except Exception:
        return None


# 등급/요약 생성
def grade_from_rate(rate: float) -> str:
    # 0~1 범위 가정
    if rate >= 0.8: return "양호"
    if rate >= 0.6: return "보통"
    return "개선필요"

def grade_mouth(delta: float) -> str:
    if delta <= -MOUTH_DELTA: return "미소"
    if delta >=  MOUTH_DELTA: return "하강"
    return "중립"

def build_feedback_summary(gaze_grade: str, blink_grade: str, mouth_grade: str) -> str:
    parts = []
    # 주시
    if gaze_grade == "양호":
        parts.append("정면 주시율은 양호합니다")
    elif gaze_grade == "보통":
        parts.append("정면 주시율은 보통 수준입니다")
    else:
        parts.append("정면 주시율 개선이 필요합니다")
    # 깜빡임
    if blink_grade == "양호":
        parts.append("깜빡임 안정도는 양호합니다")
    elif blink_grade == "보통":
        parts.append("깜빡임 안정도는 보통입니다")
    else:
        parts.append("깜빡임 빈도를 안정화하세요")
    # 입꼬리
    if mouth_grade == "미소":
        parts.append("입꼬리는 상승 경향(미소)입니다")
    elif mouth_grade == "하강":
        parts.append("입꼬리 하강 경향이 관찰됩니다")
    else:
        parts.append("입꼬리는 대체로 중립입니다")
    return " / ".join(parts) + "."


# 분석 루프
def analyze_expression_video(
    video_path: str,
    blink_limit_per_min: int = 30,
    baseline_seconds: float = 2.0,
    frame_stride: int = 5
) -> Dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError("Session video not found")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0 or np.isnan(fps): fps = 30.0

    # baseline 수집 버퍼(영상 초반)
    vbuf: List[Tuple[float,float,float,float,float,float]] = []  # yaw, pitch, ear, mouth, eye_h, eye_v
    baseline: Optional[Dict[str, float]] = None
    baseline_from_video = False

    # 지표 누적
    stats = {
        "frames": 0, "frames_head_ok": 0, "frames_eye_valid": 0,
        "frames_eye_ok": 0, "frames_head_eye_ok": 0, "blinks_count": 0
    }
    ema = {"yaw": None, "pitch": None, "ear": None, "mouth": None, "eye_h": None, "eye_v": None}
    blink_in_progress = False
    last_blink_t = 0.0

    # 주시 지표용 좌표
    gaze_head_x: List[float] = []
    gaze_head_y: List[float] = []
    gaze_both_x: List[float] = []
    gaze_both_y: List[float] = []

    idx = -1
    while True:
        ok, frame0 = cap.read()
        if not ok:
            break
        idx += 1
        if frame_stride > 1 and (idx % frame_stride) != 0:
            continue
        t = (idx / fps)

        # 리사이즈(성능)
        h0, w0 = frame0.shape[:2]
        if w0 > 640:
            scale = 640.0 / w0
            frame = cv2.resize(frame0, (640, int(h0*scale)), interpolation=cv2.INTER_AREA)
        else:
            frame = frame0

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = FACE_MESH.process(rgb)
        if not res.multi_face_landmarks:
            continue
        lms = res.multi_face_landmarks[0].landmark
        h, w = frame.shape[:2]

        # 특징 추출
        yaw, pitch = head_pose_proxy(lms, w, h)
        ear_l = ear_from_landmarks(lms, w, h, LEFT_EYE)
        ear_r = ear_from_landmarks(lms, w, h, RIGHT_EYE)
        ear = (ear_l + ear_r) / 2.0
        mouth = mouth_corners_relative(lms, w, h)

        lc, rc = iris_centers_from_landmarks(lms, w, h)
        l_off = eye_gaze_offset(lms, w, h, lc, LEFT_EYE_CORNERS, LEFT_EYE_LIDS)  if lc is not None else None
        r_off = eye_gaze_offset(lms, w, h, rc, RIGHT_EYE_CORNERS, RIGHT_EYE_LIDS) if rc is not None else None
        eye_h = np.mean([x[0] for x in [l_off, r_off] if x is not None]) if (l_off or r_off) else None
        eye_v = np.mean([x[1] for x in [l_off, r_off] if x is not None]) if (l_off or r_off) else None

        stats["frames"] += 1

        # baseline 수집
        if baseline is None and t <= baseline_seconds:
            vbuf.append((yaw, pitch, ear, mouth, eye_h or 0.0, eye_v or 0.0))

        # EMA 업데이트
        ema["yaw"]   = ema_update(ema["yaw"],   yaw)
        ema["pitch"] = ema_update(ema["pitch"], pitch)
        ema["ear"]   = ema_update(ema["ear"],   ear)
        ema["mouth"] = ema_update(ema["mouth"], mouth)
        if eye_h is not None:
            ema["eye_h"] = ema_update(ema["eye_h"], eye_h)
        if eye_v is not None:
            ema["eye_v"] = ema_update(ema["eye_v"], eye_v)

        # baseline 결정(영상 초반)
        if baseline is None and t > baseline_seconds:
            if vbuf:
                arr = np.array(vbuf, dtype=np.float32)
                yaw_b, pitch_b, ear_b, mouth_b, eye_h_b, eye_v_b = np.median(arr, axis=0)
                baseline = {
                    "yaw": float(yaw_b), "pitch": float(pitch_b),
                    "ear": float(max(1e-6, ear_b)), "mouth": float(mouth_b),
                    "eye_h": float(eye_h_b), "eye_v": float(eye_v_b)
                }
            else:
                baseline = {
                    "yaw": yaw, "pitch": pitch, "ear": max(1e-6, ear),
                    "mouth": mouth, "eye_h": eye_h or 0.0, "eye_v": eye_v or 0.0
                }
            baseline_from_video = True

        if baseline is None:
            baseline = {
                "yaw": yaw, "pitch": pitch, "ear": max(1e-6, ear),
                "mouth": mouth, "eye_h": eye_h or 0.0, "eye_v": eye_v or 0.0
            }
            baseline_from_video = True

        # 판정(머리)
        dyaw   = (ema["yaw"]   - baseline["yaw"])   if ema["yaw"]   is not None else 0.0
        dpitch = (ema["pitch"] - baseline["pitch"]) if ema["pitch"] is not None else 0.0
        HEAD_OK = (abs(dyaw) <= GAZE_OFF_ABS) and (abs(dpitch) <= GAZE_OFF_ABS)
        if HEAD_OK: stats["frames_head_ok"] += 1

        # 판정(눈)
        EYE_OK = False
        eye_h_corr, eye_v_corr = None, None
        if (ema["eye_h"] is not None) and (ema["eye_v"] is not None):
            stats["frames_eye_valid"] += 1
            eye_h_corr = ema["eye_h"] - baseline.get("eye_h", 0.0)
            eye_v_corr = ema["eye_v"] - baseline.get("eye_v", 0.0)
            EYE_OK = (abs(eye_h_corr) <= EYE_OFF_ABS) and (abs(eye_v_corr) <= EYE_OFF_ABS)
            if EYE_OK: stats["frames_eye_ok"] += 1

        # 결합
        HEAD_EYE_OK = HEAD_OK and EYE_OK
        if HEAD_EYE_OK: stats["frames_head_eye_ok"] += 1

        # 깜빡임 카운트(EAR 기반)
        eye_closed = (ema["ear"] is not None) and (ema["ear"] < baseline["ear"] * BLINK_RATIO)
        tsec = idx / fps
        if eye_closed and not blink_in_progress:
            blink_in_progress = True
            last_blink_t = tsec
        elif (not eye_closed) and blink_in_progress:
            if (tsec - last_blink_t) >= BLINK_MIN_DUR:
                stats["blinks_count"] += 1
            blink_in_progress = False

        # 좌표 저장(시선 지표)
        gaze_head_x.append(float(dyaw))
        gaze_head_y.append(float(dpitch))
        if HEAD_EYE_OK and (eye_h_corr is not None) and (eye_v_corr is not None):
            gaze_both_x.append(float(eye_h_corr))
            gaze_both_y.append(float(eye_v_corr))

    # 루프 종료
    frames_total = stats["frames"]
    cap.release()

    if frames_total == 0:
        raise HTTPException(status_code=409, detail="expression_analysis_not_ready")

    # 영상 길이(초)
    duration_sec = frames_total / (fps / max(1, frame_stride))
    dur = max(1e-6, duration_sec)

    # 주시율
    head_gaze_rate = (stats["frames_head_ok"] / max(1, frames_total)) * 100.0
    head_eye_gaze_rate = (stats["frames_head_eye_ok"] / max(1, frames_total)) * 100.0
    eye_only_gaze_rate = (stats["frames_eye_ok"] / max(1, stats["frames_eye_valid"])) * 100.0

    # 깜빡임/분
    blinks_per_min = stats["blinks_count"] / (dur / 60.0)

    # 시선 지표(고정도)
    metrics_head = compute_fixation_metrics(gaze_head_x, gaze_head_y, target=(0.0, 0.0))
    metrics_both = compute_fixation_metrics(gaze_both_x, gaze_both_y, target=(0.0, 0.0))

    
    # 점수/등급/요약 산출
    # (1) gaze: head∧eye 주시율(%) → 0~1로 정규화
    gaze_rate_norm = np.clip(head_eye_gaze_rate / 100.0, 0.0, 1.0)
    gaze_grade = grade_from_rate(gaze_rate_norm)

    # (2) blink 안정도: limit 대비 과도하면 감점 → 1 - min(1, 실제/limit)
    blink_stability = float(max(0.0, 1.0 - min(1.0, blinks_per_min / float(blink_limit_per_min))))
    blink_grade = grade_from_rate(blink_stability)

    # (3) mouth delta: 평균 mouth - baseline mouth
    
    mouth_delta_vals = np.array(gaze_head_y) * 0 
    mouth_delta = float((ema["mouth"] or baseline["mouth"]) - baseline["mouth"])
    mouth_grade = grade_mouth(mouth_delta)
    # mouth 안정 점수(0~1): |Δ|가 작을수록 1.0, MOUTH_DELTA에서 0.5 근처가 되도록 스케일
    mouth_stability = float(np.clip(1.0 - (abs(mouth_delta) / (MOUTH_DELTA * 2.0)), 0.0, 1.0))

    # 종합 점수: 가중 평균
    overall_score = float(np.clip((gaze_rate_norm*0.7 + blink_stability*0.2 + mouth_stability*0.1) * 100.0, 0.0, 100.0))

    # 피드백 요약
    feedback_summary = build_feedback_summary(gaze_grade, blink_grade, mouth_grade)

    result = {
        "head_eye_gaze_rate": {"value": round(gaze_rate_norm, 2), "rating": gaze_grade},
        "blink_stability": {"value": round(blink_stability, 2), "rating": blink_grade},
        "mouth_delta": {"value": round(mouth_delta, 3), "rating": mouth_grade},
        "fixation_metrics": {
            "MAE": safe_num(metrics_both.get("MAE")),
            "BCEA": safe_num(metrics_both.get("BCEA")),
        },
        "aux": {
            "head_gaze_rate_percent": round(head_gaze_rate, 1),
            "eye_only_gaze_rate_percent": round(eye_only_gaze_rate, 1),
            "blinks_count": int(stats["blinks_count"]),
            "blinks_per_min": safe_num(blinks_per_min),
            "baseline_source": "영상 초반 기준" if baseline_from_video else "세션 기준",
            "frames_used": int(frames_total)
        },
        "overall_score": round(overall_score, 1),
        "feedback_summary": feedback_summary
    }
    return result