from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import json
import re
import ast

# Optional: use numpy median if available; otherwise pure-Python fallback
try:
    import numpy as _np  # type: ignore
except Exception:  # pragma: no cover
    _np = None


# =========================
# Configuration (tunable)
# =========================
@dataclass
class TremorThreshold:
    z_max_good: float = 0.8
    z_max_ok: float = 1.2
    z_max_warn: float = 1.6
    jitter_penalty_thr: float = 2.5  # %
    shimmer_penalty_thr: float = 9.0  # %
    hnr_penalty_thr: float = 12.0  # dB
    penalty_step: int = 3
    floor: int = 40

@dataclass
class SpeedThreshold:
    syll_per_word: float = 2.25  # sps -> wpm conversion (KO default)
    good_min: int = 140
    good_max: int = 170
    mid1_min: int = 120
    mid1_max: int = 139
    mid2_min: int = 171
    mid2_max: int = 185
    edge1_min: int = 100
    edge1_max: int = 119
    edge2_min: int = 186
    edge2_max: int = 200

@dataclass
class PauseThreshold:
    # When using structured input: median pause_ratio bands
    med_good: float = 0.18
    med_mid: float = 0.25
    med_warn: float = 0.35

@dataclass
class Weights:
    tremor: float = 0.25
    pause: float = 0.25
    tone: float = 0.25
    speed: float = 0.25

@dataclass
class Config:
    tremor: TremorThreshold = TremorThreshold()
    speed: SpeedThreshold = SpeedThreshold()
    pause: PauseThreshold = PauseThreshold()
    weights: Weights = Weights()


# =========================
# Utilities
# =========================
def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    if _np is not None:
        return float(_np.median(vals))  # type: ignore
    vs = sorted(vals)
    n = len(vs)
    mid = n // 2
    if n % 2 == 1:
        return float(vs[mid])
    return float((vs[mid - 1] + vs[mid]) / 2.0)

def _clamp_int(x: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, round(x))))


# =========================
# Scoring (structured input)
# =========================
def _score_tremor_struct(tremor: Dict[str, Any], cfg: Config) -> Tuple[Optional[Dict[str, Any]], int, str]:
    rows = (tremor or {}).get("timeline", [])
    if not rows:
        return None, 0, "정보부족"

    z = [r.get("tremor_score") for r in rows if r.get("tremor_score") is not None]
    jit = [r.get("jitter_pct") for r in rows if r.get("jitter_pct") is not None]
    shm = [r.get("shimmer_pct") for r in rows if r.get("shimmer_pct") is not None]
    hnr = [r.get("hnr_db") for r in rows if r.get("hnr_db") is not None]
    if not z:
        return None, 0, "정보부족"

    stats = {
        "z_max": max(z),
        "jitter_pct": _median(jit),
        "shimmer_pct": _median(shm),
        "hnr_db": _median(hnr),
    }

    th = cfg.tremor
    zmax = stats["z_max"]
    if zmax < th.z_max_good:
        base, level = 90, "양호"
    elif zmax < th.z_max_ok:
        base, level = 82, "양호"
    elif zmax < th.z_max_warn:
        base, level = 70, "약간"
    else:
        base, level = 55, "주의"

    score = base
    if (stats["jitter_pct"] or 0) > th.jitter_penalty_thr: score -= th.penalty_step
    if (stats["shimmer_pct"] or 0) > th.shimmer_penalty_thr: score -= th.penalty_step
    if (stats["hnr_db"] is not None) and stats["hnr_db"] < th.hnr_penalty_thr: score -= th.penalty_step
    score = _clamp_int(score, th.floor, 100)
    return stats, score, level


def _score_speed_struct(sp_tl: Dict[str, Any], cfg: Config) -> Tuple[Optional[Dict[str, Any]], int, str]:
    rows = (sp_tl or {}).get("timeline", [])
    if not rows:
        return None, 0, "정보부족"
    sps = [r.get("speaking_rate_sps") for r in rows if r.get("speaking_rate_sps") is not None]
    if not sps:
        return None, 0, "정보부족"

    sps_avg = _median(sps) or 0.0
    wpm = _clamp_int(sps_avg * 60.0 / cfg.speed.syll_per_word, 0, 400)

    s = cfg.speed
    if s.good_min <= wpm <= s.good_max:
        score, level = 88, "적정"
    elif (s.mid1_min <= wpm <= s.mid1_max) or (s.mid2_min <= wpm <= s.mid2_max):
        score, level = 82, "적정~약간 빠름"
    elif (s.edge1_min <= wpm <= s.edge1_max) or (s.edge2_min <= wpm <= s.edge2_max):
        score, level = 74, "빠름/느림"
    else:
        score, level = 60, "과속/과늦"

    return {"sps": round(sps_avg, 2), "wpm": int(wpm)}, score, level


def _score_pause_struct(sp_tl: Dict[str, Any], cfg: Config) -> Tuple[Dict[str, Any], int, str]:
    rows = (sp_tl or {}).get("timeline", [])
    if not rows:
        return {"status": "정보부족"}, 80, "보통"
    pr = [r.get("pause_ratio") for r in rows if r.get("pause_ratio") is not None]
    if not pr:
        return {"status": "정보부족"}, 80, "보통"

    p_med = float(_median(pr))
    p = cfg.pause
    if p_med <= p.med_good:
        return {"status": "양호", "avg": p_med}, 85, "양호"
    if p_med <= p.med_mid:
        return {"status": "약간", "avg": p_med}, 78, "약간"
    if p_med <= p.med_warn:
        return {"status": "주의", "avg": p_med}, 70, "주의"
    return {"status": "과다", "avg": p_med}, 62, "과다"


def _build_summary(t_level: str, s_level: str, p_level: str, tone_label: Optional[str]) -> str:
    bits: List[str] = []
    if t_level in ("양호", "약간"):
        bits.append("전반적으로 안정적")
    if s_level.startswith("적정"):
        bits.append("속도 적정")
    elif "빠름" in s_level:
        bits.append("속도는 다소 빠름")
    if p_level == "양호":
        bits.append("불필요한 긴 침묵은 없음")
    if tone_label:
        bits.append(f"억양은 {tone_label}")
    return (". ".join(bits) + ".") if bits else ""


def build_payload_from_structures(
    tremor: Dict[str, Any],
    sp_tl: Dict[str, Any],
    tone: Dict[str, Any],
    cfg: Config = Config(),
) -> Dict[str, Any]:
    """
    Args:
        tremor: dict with 'timeline' list (each item may include tremor_score, jitter_pct, shimmer_pct, hnr_db)
        sp_tl:  dict with 'timeline' list (each item may include speaking_rate_sps, pause_ratio, ...)
        tone:   dict with 'tone_score' (0-100), 'label', and optional drivers
        cfg:    Config
    Returns:
        Frontend-ready payload dict: { total_score, summary, metrics: [ ... ] }
    """
    t_stats, t_score, t_level = _score_tremor_struct(tremor, cfg)
    s_stats, s_score, s_level = _score_speed_struct(sp_tl, cfg)
    p_info,  p_score, p_level = _score_pause_struct(sp_tl, cfg)

    tone_score = int(tone.get("tone_score", 0))
    tone_label = tone.get("label")

    w = cfg.weights
    total = _clamp_int(
        w.tremor * t_score +
        w.pause  * p_score +
        w.tone   * tone_score +
        w.speed  * s_score,
        0, 100
    )

    payload = {
        "total_score": total,
        "summary": _build_summary(t_level, s_level, p_level, tone_label),
        "metrics": [
            {
                "id": "tremor", "label": "떨림",
                "score": t_score, "level": t_level,
                "value": None, "unit": None,
                "description": (
                    f"최대 z={t_stats['z_max']:.2f}, "
                    f"jitter≈{(t_stats.get('jitter_pct') or 0):.2f}%, "
                    f"shimmer≈{(t_stats.get('shimmer_pct') or 0):.2f}%, "
                    f"HNR≈{(t_stats.get('hnr_db') or 0):.1f} dB"
                ) if t_stats else "정보 부족",
                "details": t_stats or {}
            },
            {
                "id": "pause", "label": "공백",
                "score": p_score, "level": p_level,
                "value": p_info.get("avg"), "unit": "ratio",
                "description": "불필요한 침묵 과다는 없음." if p_level == "양호" else "휴지 개선 필요."
            },
            {
                "id": "tone", "label": "억양",
                "score": min(100, max(0, tone_score)),
                "level": "양호" if tone_score >= 80 else "보통",
                "value": tone_label, "unit": None,
                "description": "억양 변화와 에너지 밸런스가 안정적." if tone_score >= 80 else "억양 개선 여지 있음.",
                "details": {k: v for k, v in tone.items() if k != "label"}
            },
            {
                "id": "speed", "label": "속도",
                "score": s_score, "level": s_level,
                "value": (s_stats or {}).get("wpm"), "unit": "wpm",
                "description": "말하기 속도가 빠른 편이나 명료성은 유지." if s_stats else "정보 부족",
                "details": s_stats or {}
            }
        ]
    }
    return payload


# =====================================
# Fallback: console-text parsing path
# =====================================
_HEADER_RE = re.compile(r"^=== \[(TREMOR|SPEED|PAUSE|TONE)\][^\n]*$", re.M)

def _extract_blocks(raw_text: str) -> Dict[str, str]:
    blocks: Dict[str, str] = {}
    matches = list(_HEADER_RE.finditer(raw_text))
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        blocks[name] = raw_text[start:end].strip()
    return blocks

def _parse_tremor_text(block: str) -> Optional[Dict[str, float]]:
    zmax, jit, shm, hnr = [], [], [], []
    for line in block.splitlines():
        m = re.search(r"z_max\s*=\s*([0-9.]+)", line);        zmax += [float(m.group(1))] if m else []
        j = re.search(r"jitter~([0-9.]+)%", line);            jit  += [float(j.group(1))] if j else []
        s = re.search(r"shimmer~([0-9.]+)%", line);           shm  += [float(s.group(1))] if s else []
        h = re.search(r"HNR~([0-9.]+)\s*dB", line);           hnr  += [float(h.group(1))] if h else []
    if not zmax:
        return None
    def mean(x): return sum(x)/len(x) if x else None
    return {
        "z_max": max(zmax),
        "jitter_pct": mean(jit),
        "shimmer_pct": mean(shm),
        "hnr_db": mean(hnr),
    }

def _parse_speed_text(block: str, syll_per_word: float) -> Optional[Dict[str, Any]]:
    sps = [float(x) for x in re.findall(r"speaking~([0-9.]+)\s*sps", block)]
    if not sps:
        return None
    sps_avg = sum(sps)/len(sps)
    wpm = int(round(sps_avg * 60.0 / syll_per_word))
    return {"sps": sps_avg, "wpm": wpm}

def _parse_pause_text(block: str) -> Dict[str, Any]:
    if "없음" in block:
        return {"status": "양호"}
    m = re.search(r"평균\s*([0-9.]+)\s*s", block)
    return {"status": "정보부족", "avg": float(m.group(1))} if m else {"status": "정보부족"}

def build_payload_from_console_text(raw_text: str, cfg: Config = Config()) -> Dict[str, Any]:
    """
    Input: console text that includes
      === [TREMOR] ...
      === [SPEED] ...
      === [PAUSE] ...
      === [TONE] ...
    """
    blocks = _extract_blocks(raw_text)
    tremor_stats = _parse_tremor_text(blocks.get("TREMOR", ""))
    speed_stats  = _parse_speed_text(blocks.get("SPEED", ""), cfg.speed.syll_per_word)
    pause_info   = _parse_pause_text(blocks.get("PAUSE", ""))

    # Score by reusing structured scorers with an adapter
    t_score, t_level = 0, "정보부족"
    if tremor_stats:
        t_stats, t_score, t_level = _score_tremor_struct({"timeline":[
            {"tremor_score": tremor_stats["z_max"],
             "jitter_pct": tremor_stats.get("jitter_pct"),
             "shimmer_pct": tremor_stats.get("shimmer_pct"),
             "hnr_db": tremor_stats.get("hnr_db")}
        ]}, cfg)
        tremor_stats = t_stats

    s_score, s_level = 0, "정보부족"
    if speed_stats:
        s_stats, s_score, s_level = _score_speed_struct({"timeline":[
            {"speaking_rate_sps": speed_stats["sps"]}
        ]}, cfg)
        speed_stats = s_stats

    p_info_struct, p_score, p_level = _score_pause_struct({"timeline":[
        {"pause_ratio": pause_info.get("avg")} if "avg" in pause_info else {}
    ]}, cfg)

    tone_dict: Dict[str, Any]
    if "TONE" in blocks:
        try:
            tone_dict = ast.literal_eval(blocks["TONE"].strip())
        except Exception:
            tone_dict = {}
    else:
        m = re.search(r"\{.*\}", raw_text, re.S)
        tone_dict = ast.literal_eval(m.group(0)) if m else {}
    tone_score = int(tone_dict.get("tone_score", 0))
    tone_label = tone_dict.get("label")

    w = cfg.weights
    total = _clamp_int(w.tremor * t_score + w.pause * p_score + w.tone * tone_score + w.speed * s_score, 0, 100)

    return {
        "total_score": total,
        "summary": _build_summary(t_level, s_level, p_level, tone_label),
        "metrics": [
            {"id":"tremor","label":"떨림","score":t_score,"level":t_level,
             "value":None,"unit":None,
             "description":(
                 f"최대 z={tremor_stats['z_max']:.2f}, "
                 f"jitter≈{(tremor_stats.get('jitter_pct') or 0):.2f}%, "
                 f"shimmer≈{(tremor_stats.get('shimmer_pct') or 0):.2f}%, "
                 f"HNR≈{(tremor_stats.get('hnr_db') or 0):.1f} dB"
             ) if tremor_stats else "정보 부족",
             "details": tremor_stats or {}},
            {"id":"pause","label":"공백","score":p_score,"level":p_level,
             "value":p_info_struct.get("avg"),"unit":"ratio",
             "description":"불필요한 침묵 과다는 없음." if p_level=="양호" else "휴지 개선 필요."},
            {"id":"tone","label":"억양",
             "score":min(100,max(0,tone_score)),"level":"양호" if tone_score>=80 else "보통",
             "value":tone_label,"unit":None,
             "description":"억양 변화와 에너지 밸런스가 안정적." if tone_score>=80 else "억양 개선 여지 있음.",
             "details": {k:v for k,v in tone_dict.items() if k!='label'}},
            {"id":"speed","label":"속도","score":s_score,"level":s_level,
             "value":(speed_stats or {}).get("wpm"),"unit":"wpm",
             "description":"말하기 속도가 빠른 편이나 명료성은 유지." if speed_stats else "정보 부족",
             "details": speed_stats or {}},
        ]
    }


# =========================
# JSON helper
# =========================
def to_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
