
# ultra-lean vocalization core (no plotting, no colab/drive)
import os
import numpy as np
import pandas as pd
import parselmouth as pm
from parselmouth.praat import call
import soundfile as sf

# =====================
# CONFIGS (edit here)
# =====================
PROSODY_CFG = {
    "win": 0.5,
    "hop": 0.2,
    # speaking/pause
    "speaking_band": (3.5, 5.0),
    "pause_ratio_band": (0.15, 0.35),
    "syllable_min_sep": 0.12,
    "pause_min_dur": 0.20,
    "pause_db_drop": 6.0,
    # F0
    "f0_min": 75, "f0_max": 500,
    "ending_slope_window": 0.8,
    # energy
    "stress_top_percent": 10,
    # Tremor refs/weights
    "jitter_ref_pct": 2.0,
    "shimmer_ref_pct": 6.0,
    "hnr_good_db": 18.0,
    "tremor_weights": {"jitter":0.18,"shimmer":0.17,"hnr":0.10,"fm":0.35,"am":0.20},
    # AM/FM
    "amfm_band": (3.0, 10.0),
    "amfm_ref_percentile": 90,
    # HNR viz band (unused here, kept for compatibility)
    "hnr_band": (15.0, 22.0),
    # highlight k (unused in core)
    "k_highlight": 5,
}

Z_PARAMS = dict(
    win_sec=4.0,
    z_hi=1.10,
    z_lo=0.6,
    min_dur=0.6,
    merge_gap=0.3,
    min_consec_frames=3
)

PAD_MS = 150

SPEED_PARAMS = dict(
    fast_hi=6.1, fast_lo=5.6,
    slow_lo=2.6, slow_hi=3.2,
    min_hold=1.0,
    merge_gap=0.5
)

VOICED_THR     = 0.65
FAST_MAX_PAUSE = 0.26
SLOW_MIN_PAUSE = 0.25

# ===== Tone config =====
TONE_CFG = {
    "f0_range_target": (4.0, 8.5),
    "ending_slope_ok": (1.2, 3.5),
    "pitch_var_target": (1.2, 4.0),
    "intonation_sub_weights": {"range": 0.65, "slope": 0.20, "var": 0.15},
    "stress_rate_target": (0.08, 0.20),
    "energy_var_db_target": (2.5, 6.0),
    "energy_balance_tol": 0.15,
    "npvi_target": (30.0, 65.0),
    "syll_cv_target": (0.12, 0.28),
    "regularity_target": (0.65, 0.90),
    "weights": {"intonation": 0.40, "energy": 0.30, "rhythm": 0.30},
    "monotone_guards": {"range_lo": 3.2, "var_lo": 1.2, "cap": 0.50}
}

# =====================
# IO
# =====================
def load_sound(path: str) -> pm.Sound:
    """Load audio file into parselmouth.Sound. Supports wav/flac/ogg/mp3 via temporary wav if needed."""
    # parselmouth handles wav/aiif directly; use soundfile to convert others
    ext = os.path.splitext(path)[1].lower()
    if ext in (".wav", ".aiff", ".aif"):
        return pm.Sound(path)
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        sf.write(tmp.name, y, sr, subtype="PCM_16")
        temp_path = tmp.name
    try:
        return pm.Sound(temp_path)
    finally:
        try: os.remove(temp_path)
        except: pass

# =====================
# Helpers
# =====================
def sliding_windows(dur, win, hop):
    t = 0.0
    out = []
    while t < dur - 1e-9:
        t0 = t
        t1 = min(dur, t + win)
        out.append((t0, t1))
        t += hop
    return out

def safe_percentile(x, p):
    arr = np.asarray(list(x), dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0: return None
    return float(np.percentile(arr, p))

def band_energy(x, fs, lo, hi, order=3):
    """Simple FFT band energy between lo..hi Hz (works for evenly-sampled series)."""
    x = np.asarray(x, dtype=float)
    if x.size < 8: return 0.0
    x = x - np.nanmean(x)
    x[np.isnan(x)] = 0.0
    n = int(2**np.ceil(np.log2(len(x))))
    X = np.fft.rfft(x, n=n)
    freqs = np.fft.rfftfreq(n, d=1.0/fs)
    band = (freqs >= lo) & (freqs <= hi)
    if not band.any(): return 0.0
    power = (np.abs(X)**2)[band]
    return float(np.sum(power) / max(band.sum(),1))

def _ensure_center(df: pd.DataFrame) -> pd.DataFrame:
    if "center" not in df.columns:
        df = df.copy()
        df["center"] = (df["start"] + df["end"]) / 2.0
    return df

def make_voiced_mask(sound, pitch_obj=None):
    cfg = PROSODY_CFG
    pitch = pitch_obj or call(sound, "To Pitch", 0.0, cfg["f0_min"], cfg["f0_max"])
    dt = pitch.get_time_step() or 0.01
    D  = sound.get_total_duration()
    times = np.arange(0, D, dt, dtype=float)
    f0  = np.array([float(call(pitch, "Get value at time", float(t), "Hertz", "Linear") or 0.0) for t in times])
    voiced = f0 > 0
    pad_frames = int((PAD_MS/1000.0)/dt)
    if pad_frames > 0:
        idx = np.where(voiced)[0]
        for i in idx:
            lo = max(0, i - pad_frames); hi = min(len(voiced), i + pad_frames + 1)
            voiced[lo:hi] = True
    return times, voiced, dt

# =====================
# Tremor (jitter/shimmer/HNR + AM/FM)
# =====================
def eval_tremor(sound, f0_min=75, f0_max=500, win=1.0, hop=0.5, use_amfm=True):
    cfg = PROSODY_CFG
    dur = sound.get_total_duration()
    pp   = call(sound, "To PointProcess (periodic, cc)", f0_min, f0_max)
    harm = call(sound, "To Harmonicity (cc)", 0.01, f0_min, 0.1, 1.0)
    T_min, T_max = 1.0/f0_max, 1.0/f0_min

    rows = []
    fm_pool, am_pool = [], []

    for t0, t1 in sliding_windows(dur, win, hop):
        jitter = call(pp, "Get jitter (local)", t0, t1, T_min, T_max, 1.3)               # fraction
        shimmer= call([sound, pp], "Get shimmer (local)", t0, t1, T_min, T_max, 1.3, 1.6)# fraction
        hnr    = call(harm, "Get mean", t0, t1)                                         # dB
        jit_pct, shm_pct, hnr_db = float(jitter*100.0), float(shimmer*100.0), float(hnr)

        fmE = amE = 0.0
        if use_amfm:
            # FM: from Pitch
            pitch = call(sound, "To Pitch", 0.01, f0_min, f0_max)
            dt = pitch.get_time_step() or 0.01
            n = max(int((t1-t0)/dt), 3)
            f0_vals = []
            for i in range(n):
                try:
                    v = call(pitch, "Get value in frame", int((t0/dt))+i+1)
                except:
                    v = np.nan
                f0_vals.append(v)
            f0 = np.array(f0_vals, float)
            idx = np.arange(n)
            if np.isfinite(f0).any():
                mask = (f0>0)&np.isfinite(f0)
                if mask.any():
                    f0 = np.where(mask, f0, np.nan)
                    f0 = np.interp(idx, idx[~np.isnan(f0)], f0[~np.isnan(f0)])
                    lo, hi = cfg["amfm_band"]
                    fmE = band_energy(f0, fs=1.0/dt, lo=lo, hi=hi, order=3)

            # AM: Intensity series
            intensity = call(sound, "To Intensity", 75.0, 0.0)
            nI = int(call(intensity, "Get number of frames"))
            if nI > 3:
                times = np.array([call(intensity, "Get time from frame number", i+1) for i in range(nI)])
                vals  = np.array([call(intensity, "Get value in frame", i+1) for i in range(nI)])
                mask = (times>=t0)&(times<=t1)
                it, iv = times[mask], np.nan_to_num(vals[mask], nan=0.0)
                if it.size >= 3:
                    dtI = np.mean(np.diff(it))
                    grid = np.arange(it[0], it[-1]+1e-9, dtI)
                    ivu = np.interp(grid, it, iv)
                    lo, hi = cfg["amfm_band"]
                    amE = band_energy(ivu, fs=1.0/dtI, lo=lo, hi=hi, order=3)

            fm_pool.append(fmE); am_pool.append(amE)

        rows.append({
            "start": round(t0,3), "end": round(t1,3),
            "jitter_pct": round(jit_pct,3),
            "shimmer_pct": round(shm_pct,3),
            "hnr_db": round(hnr_db,3),
            "fm_4_12": round(fmE,5), "am_4_12": round(amE,5)
        })

    # Normalize to percentile refs
    P = cfg["amfm_ref_percentile"]
    fm_ref = safe_percentile(fm_pool, P) or 1.0
    am_ref = safe_percentile(am_pool, P) or 1.0

    out = []
    JREF = cfg["jitter_ref_pct"]
    SREF = cfg["shimmer_ref_pct"]
    HREF = cfg["hnr_good_db"]
    W    = cfg["tremor_weights"]

    for r in rows:
        sj = np.clip(r["jitter_pct"]/JREF, 0, 1)
        ss = np.clip(r["shimmer_pct"]/SREF, 0, 1)
        sh = np.clip((HREF - r["hnr_db"])/max(HREF,1e-6), 0, 1)
        fmN = np.clip((r["fm_4_12"]/fm_ref), 0, 1) if use_amfm else 0.0
        amN = np.clip((r["am_4_12"]/am_ref), 0, 1) if use_amfm else 0.0
        tremor = (W["jitter"]*sj + W["shimmer"]*ss + W["hnr"]*sh + W["fm"]*fmN + W["am"]*amN)
        out.append({**r, "tremor_score": round(float(tremor),3)})

    # global
    jitter_g = call(pp, "Get jitter (local)", 0, 0, T_min, T_max, 1.3)*100.0
    shimmer_g= call([sound, pp], "Get shimmer (local)", 0, 0, T_min, T_max, 1.3, 1.6)*100.0
    hnr_g    = call(harm, "Get mean", 0, 0)

    return {"summary": {
                "duration_s": round(dur,2),
                "jitter_pct": round(float(jitter_g),2),
                "shimmer_pct": round(float(shimmer_g),2),
                "hnr_db": round(float(hnr_g),2)
            },
            "timeline": out}

# =====================
# Speed / Pause (timeline)
# =====================
def _intensity_series(sound):
    inten = call(sound, "To Intensity", 75.0, 0.0)
    n = int(call(inten, "Get number of frames"))
    if n < 2:
        return np.array([0.0]), np.array([0.0])
    t = np.array([call(inten, "Get time from frame number", i+1) for i in range(n)], float)
    v = np.array([call(inten, "Get value in frame", i+1) for i in range(n)], float)
    v = np.nan_to_num(v, nan=np.nanmedian(v))
    return t, v

def _syllable_peaks(times, vals, min_sep):
    """Very light-weight peak picker on intensity derivative."""
    if len(times) < 3: return np.array([])
    dv = np.diff(vals)
    dt = np.diff(times)
    s = np.zeros_like(vals)
    s[1:] = dv / np.maximum(dt, 1e-6)
    # local maxima on s -> approximate syllable pulses
    peaks = []
    last_t = -1e9
    for i in range(1, len(s)-1):
        if s[i-1] < s[i] and s[i] > s[i+1]:  # simple peak
            if times[i] - last_t >= min_sep:
                peaks.append(times[i])
                last_t = times[i]
    return np.array(peaks)

def eval_speed_pause_timeline(sound, win=None, hop=None):
    cfg = PROSODY_CFG
    win = win or cfg["win"]; hop = hop or cfg["hop"]
    D = sound.get_total_duration()
    tI, vI = _intensity_series(sound)
    med = pd.Series(vI).rolling(9, center=True, min_periods=3).median().bfill().ffill().values
    # Pause mask by dB drop
    enter = med - cfg["pause_db_drop"]
    speaking = vI >= enter
    # syllable peaks
    peaks = _syllable_peaks(tI, vI, cfg["syllable_min_sep"])

    rows = []
    for t0, t1 in sliding_windows(D, win, hop):
        mask = (tI >= t0) & (tI <= t1)
        dur = (t1 - t0)
        if mask.any():
            # pause ratio (frames below enter) length-weighted by dt
            dt = np.diff(tI[mask]).mean() if mask.sum() > 1 else win/5.0
            pr = float(np.mean(~speaking[mask]))
        else:
            pr = 0.0
        # speaking/articulation rate from peaks count
        nsy = int(((peaks >= t0) & (peaks <= t1)).sum())
        sps = nsy / max(dur, 1e-6)
        rows.append({
            "start": round(t0,3), "end": round(t1,3),
            "speaking_rate_sps": round(float(sps), 2),
            "articulation_rate_sps": round(float(sps), 2),
            "pause_ratio": round(float(pr), 2),
            "voiced_ratio": 1.0 - round(float(pr), 2)  # crude proxy
        })
    return {"timeline": rows}

# =====================
# Intonation / Energy / Rhythm
# =====================
def hz_to_st_ratio(a, b):
    a = float(a); b = float(b)
    if a <= 0 or b <= 0: return np.nan
    return 12.0 * np.log2(a / b)

def robust_eval_intonation(sound, f0_min=75, f0_max=500, ending_win=None):
    cfg = PROSODY_CFG
    if ending_win is None: ending_win = cfg["ending_slope_window"]
    pitch = call(sound, "To Pitch", 0.0, f0_min, f0_max)
    D = sound.get_total_duration()
    dt = pitch.get_time_step() or 0.01
    times = np.arange(0, D, dt)
    f0 = np.array([float(call(pitch, "Get value at time", float(t), "Hertz", "Linear") or 0.0) for t in times])
    valid = (f0 > 0) & np.isfinite(f0)
    f0v = f0[valid]
    if f0v.size < 10:
        return {"summary": {"f0_range_st": 0.0, "ending_slope_hz_per_s": 0.0, "pitch_var_st": 0.0}}
    p10, p90 = np.percentile(f0v, [10, 90])
    f0_range_st = hz_to_st_ratio(p90, p10) if (p10 > 0) else 0.0
    f0_med = np.median(f0v)
    st_series = 12.0 * np.log2(f0v / f0_med)
    pitch_var_st = float(np.std(st_series))
    w0 = max(0.0, D - ending_win); w1 = D
    mask_end = (times >= w0) & (times <= w1) & valid
    if mask_end.sum() >= 5:
        tt = times[mask_end] - times[mask_end][0]
        yy = f0[mask_end]
        slope = float(np.polyfit(tt, yy, 1)[0])
    else:
        slope = 0.0
    return {"summary": {
        "f0_range_st": round(float(f0_range_st), 2),
        "ending_slope_hz_per_s": round(float(slope), 2),
        "pitch_var_st": round(float(pitch_var_st), 2),
        "f0_p10_hz": round(float(p10), 1),
        "f0_p90_hz": round(float(p90), 1),
        "f0_median_hz": round(float(f0_med), 1)
    }}

def eval_energy(sound):
    tI, vI = _intensity_series(sound)
    if vI.size < 3:
        return {"summary": {"stress_rate": None, "energy_var_db": None, "balance": None}}
    # Stress frames: top X%
    top = np.percentile(vI, 100 - PROSODY_CFG["stress_top_percent"])
    stress_rate = float((vI >= top).mean())
    energy_var = float(np.std(vI))
    # balance: first vs second half mean diff normalized
    mid = len(vI)//2
    bal = float(abs(vI[:mid].mean() - vI[mid:].mean()) / max(vI.std(), 1e-6))
    return {"summary": {
        "stress_rate": round(stress_rate, 3),
        "energy_var_db": round(energy_var, 2),
        "balance": round(bal, 3)
    }}

def eval_rhythm_timing(sound):
    # Use intensity peaks as syllable proxy, compute timing variability
    tI, vI = _intensity_series(sound)
    peaks = _syllable_peaks(tI, vI, PROSODY_CFG["syllable_min_sep"])
    if peaks.size < 4:
        return {"summary": {"npvi": None, "syll_cv": None, "regularity": None}}
    iois = np.diff(peaks)
    mean_ioi = float(np.mean(iois))
    cv = float(np.std(iois) / max(mean_ioi, 1e-6))
    # nPVI
    pairs = (iois[:-1], iois[1:])
    npvi = float(np.mean(200.0 * np.abs(pairs[0]-pairs[1]) / (pairs[0]+pairs[1]+1e-9)))
    regularity = float(np.clip(1.0 - cv, 0.0, 1.0))
    return {"summary": {
        "npvi": round(npvi, 1),
        "syll_cv": round(cv, 3),
        "regularity": round(regularity, 3)
    }}

# =====================
# Grouping / Reporting
# =====================
def _merge_tremor_speed(tremor: dict, sp_tl: dict) -> pd.DataFrame:
    if "timeline" not in tremor or "timeline" not in sp_tl:
        raise ValueError("merge inputs must contain 'timeline' keys.")
    t = _ensure_center(pd.DataFrame(tremor["timeline"]).copy()).sort_values("center")
    s = _ensure_center(pd.DataFrame(sp_tl["timeline"]).copy()).sort_values("center")
    hop_guess = float(np.median(np.diff(t["center"]))) if len(t) > 1 else PROSODY_CFG["hop"]
    tol = pd.Timedelta(seconds=max(hop_guess/2, 0.2))
    base = pd.Timestamp("2000-01-01")
    def add_ts(df):
        df = df.copy()
        df["ts"] = [base + pd.Timedelta(seconds=x) for x in df["center"]]
        return df
    t, s = map(add_ts, (t, s))
    merged = pd.merge_asof(t.sort_values("ts"), s.sort_values("ts"),
                           on="ts", direction="nearest", tolerance=tol, suffixes=("","_sp"))
    return merged

def tremor_z_segments(timeline_df: pd.DataFrame, win_sec: float, z_hi: float, z_lo: float,
                      min_dur: float, merge_gap: float, min_consec_frames: int,
                      voiced_mask=None, dt=None):
    df = _ensure_center(timeline_df.copy()).sort_values("center")
    centers = df["center"].values
    if len(centers) < 3: return []
    hop = float(np.median(np.diff(centers)))
    k = max(1, int(win_sec / max(hop, 1e-6)))
    med = df["tremor_score"].rolling(window=k, min_periods=max(3, k//3), center=True).median()
    med = med.bfill().ffill()
    baseline = med.replace(0, med.median())
    z = df["tremor_score"] / baseline
    valid = np.ones(len(df), dtype=bool)
    if (voiced_mask is not None) and (dt is not None):
        idx = (centers / dt).astype(int)
        idx = np.clip(idx, 0, len(voiced_mask)-1)
        valid &= voiced_mask[idx]
    segs = []
    in_run = False; run_start = None; consec = 0
    for i, (ok, zi) in enumerate(zip(valid, z.values)):
        if not ok or np.isnan(zi):
            if in_run:
                dur = df.iloc[i-1]["end"] - df.iloc[run_start]["start"]
                if dur >= min_dur:
                    segs.append({"start": float(df.iloc[run_start]["start"]),
                                 "end":   float(df.iloc[i-1]["end"]),
                                 "rows":  df.iloc[run_start:i].copy(),
                                 "z_max": float(np.nanmax(z.values[run_start:i]))})
            in_run = False; run_start = None; consec = 0
            continue
        if not in_run:
            if zi >= z_hi:
                consec += 1
                if consec >= min_consec_frames:
                    in_run = True
                    run_start = i - consec + 1
            else:
                consec = 0
        else:
            if zi < z_lo:
                dur = df.iloc[i-1]["end"] - df.iloc[run_start]["start"]
                if dur >= min_dur:
                    segs.append({"start": float(df.iloc[run_start]["start"]),
                                 "end":   float(df.iloc[i-1]["end"]),
                                 "rows":  df.iloc[run_start:i].copy(),
                                 "z_max": float(np.nanmax(z.values[run_start:i]))})
                in_run = False; run_start = None; consec = 0
    if in_run and run_start is not None:
        dur = df.iloc[len(df)-1]["end"] - df.iloc[run_start]["start"]
        if dur >= min_dur:
            segs.append({"start": float(df.iloc[run_start]["start"]),
                         "end":   float(df.iloc[len(df)-1]["end"]),
                         "rows":  df.iloc[run_start:len(df)].copy(),
                         "z_max": float(np.nanmax(z.values[run_start:len(df)]))})
    merged = []
    for s in segs:
        if not merged: merged.append(s); continue
        if s["start"] - merged[-1]["end"] <= merge_gap:
            merged[-1]["end"]  = s["end"]
            merged[-1]["rows"] = pd.concat([merged[-1]["rows"], s["rows"]], ignore_index=True)
            merged[-1]["z_max"]= max(merged[-1]["z_max"], s["z_max"])
        else:
            merged.append(s)
    return merged

def add_speed_smoothing(df, sec=1.0):
    df = df.copy()
    hop = float(np.median(np.diff(df["center"]))) if len(df) > 1 else PROSODY_CFG["hop"]
    k = max(3, int(sec / max(hop, 1e-6)))
    def roll_med(x):
        s = pd.Series(x)
        return s.rolling(k, center=True, min_periods=max(3, k//3)).median().bfill().ffill()
    for col in ["speaking_rate_sps", "articulation_rate_sps", "pause_ratio", "voiced_ratio"]:
        if col in df.columns:
            df[col + "_sm"] = roll_med(df[col].values)
    return df

def detect_speed_spans(df):
    p = SPEED_PARAMS
    df = _ensure_center(df.copy()).sort_values("center")
    df = add_speed_smoothing(df, sec=1.0)
    rate_col = "articulation_rate_sps_sm" if "articulation_rate_sps_sm" in df.columns else "speaking_rate_sps_sm"
    pause_col = "pause_ratio_sm" if "pause_ratio_sm" in df.columns else "pause_ratio"
    voiced_col = "voiced_ratio"
    def ok_fast(r):
        return (float(r.get(rate_col, np.nan)) > p["fast_hi"]) and \
               (float(r.get(pause_col, 0.0)) < FAST_MAX_PAUSE) and \
               (float(r.get(voiced_col, 1.0)) >= VOICED_THR)
    def ex_fast(v): return v < p["fast_lo"]
    def ok_slow(r):
        return (float(r.get(rate_col, np.nan)) < p["slow_lo"]) and \
               (float(r.get(pause_col, 1.0)) > SLOW_MIN_PAUSE) and \
               (float(r.get(voiced_col, 1.0)) >= VOICED_THR)
    def ex_slow(v): return v > p["slow_hi"]
    def _collect(df, enter_fn, exit_fn):
        segs, cur = [], None
        for _, r in df.iterrows():
            val = float(r.get(rate_col, np.nan))
            if not np.isfinite(val):
                if cur is not None:
                    dur = cur["end"] - cur["start"]
                    if dur >= p["min_hold"]: segs.append(cur)
                    cur = None
                continue
            if cur is None:
                if enter_fn(r):
                    cur = {"start": float(r["start"]), "end": float(r["end"]), "rows":[r]}
            else:
                if exit_fn(val):
                    dur = cur["end"] - cur["start"]
                    if dur >= p["min_hold"]: segs.append(cur)
                    cur = None
                else:
                    cur["end"] = float(r["end"]); cur["rows"].append(r)
        if cur is not None and (cur["end"]-cur["start"]) >= p["min_hold"]:
            segs.append(cur)
        merged = []
        for s in segs:
            if not merged: merged.append(s); continue
            if s["start"] - merged[-1]["end"] <= p["merge_gap"]:
                merged[-1]["end"]  = s["end"]
                merged[-1]["rows"] = merged[-1]["rows"] + s["rows"]
            else:
                merged.append(s)
        return merged
    fast, slow = _collect(df, ok_fast, ex_fast), _collect(df, ok_slow, ex_slow)
    def summarize(segs):
        out=[]
        for s in segs:
            rows = pd.DataFrame(s["rows"])
            speak_med = rows["speaking_rate_sps_sm"].median() if "speaking_rate_sps_sm" in rows else rows.get("speaking_rate_sps", pd.Series([np.nan])).median()
            artic_med = rows["articulation_rate_sps_sm"].median() if "articulation_rate_sps_sm" in rows else rows.get("articulation_rate_sps", pd.Series([np.nan])).median()
            pause_med = rows[pause_col].median() if pause_col in rows else np.nan
            out.append({
                "start": round(s["start"],2),
                "end":   round(s["end"],2),
                "speaking_med": round(float(speak_med),2) if np.isfinite(speak_med) else None,
                "artic_med":    round(float(artic_med),2) if np.isfinite(artic_med) else None,
                "pause_med":    round(float(pause_med),2) if np.isfinite(pause_med) else None,
            })
        return out
    return summarize(fast), summarize(slow)

def detect_grouped_with_cfg(sound, tremor: dict, sp_tl: dict, pitch_obj=None, use_voiced=True):
    grid, voiced, dt = (None, None, None)
    if use_voiced:
        grid, voiced, dt = make_voiced_mask(sound, pitch_obj=pitch_obj)
    merged = _merge_tremor_speed(tremor, sp_tl)

    # Tremor via z-gating
    tremor_df = pd.DataFrame(tremor["timeline"]).copy()
    tremor_df = _ensure_center(tremor_df).sort_values("center")
    segs = tremor_z_segments(
        tremor_df, Z_PARAMS["win_sec"], Z_PARAMS["z_hi"], Z_PARAMS["z_lo"],
        Z_PARAMS["min_dur"], Z_PARAMS["merge_gap"], Z_PARAMS["min_consec_frames"],
        voiced_mask=voiced, dt=dt
    )
    tremor_events = []
    for s in segs:
        rows = s["rows"]
        tremor_events.append({
            "start": round(s["start"],2),
            "end":   round(s["end"],2),
            "tremor_med": round(float(rows["tremor_score"].median()),3),
            "tremor_max": round(float(rows["tremor_score"].max()),3),
            "jitter_med_pct":  round(float(rows["jitter_pct"].median()),2),
            "shimmer_med_pct": round(float(rows["shimmer_pct"].median()),2),
            "hnr_med_db":      round(float(rows["hnr_db"].median()),1),
            "z_max":           round(float(s["z_max"]),2)
        })

    # speed/pause flags
    df = merged.copy()
    lo, hi = PROSODY_CFG["speaking_band"]
    plo, phi = PROSODY_CFG["pause_ratio_band"]
    df["flag_speed_fast"] = df["speaking_rate_sps"] > hi
    df["flag_speed_slow"] = df["speaking_rate_sps"] < lo
    df["flag_pause_low"]  = df["pause_ratio"] < plo
    df["flag_pause_high"] = df["pause_ratio"] > phi

    speed_fast, speed_slow = detect_speed_spans(merged.copy())

    def spans(flag_col):
        segs = []
        cur = None
        for _, r in df.iterrows():
            if r.get(flag_col, False):
                if cur is None:
                    cur = {"start": float(r["start"]), "end": float(r["end"]), "rows":[r]}
                else:
                    cur["end"] = float(r["end"]); cur["rows"].append(r)
            else:
                if cur is not None:
                    segs.append(cur); cur = None
        if cur is not None:
            segs.append(cur)
        out = []
        for s in segs:
            rows = pd.DataFrame(s["rows"])
            out.append({
                "start": round(s["start"],2),
                "end":   round(s["end"],2),
                "speaking_med": round(float(rows.get("speaking_rate_sps", pd.Series([np.nan])).median()),2),
                "artic_med":    round(float(rows.get("articulation_rate_sps", pd.Series([np.nan])).median()),2),
                "pause_med":    round(float(rows.get("pause_ratio", pd.Series([np.nan])).median()),2),
            })
        return out

    pause_low  = []  # optionally hide low-pause logs
    pause_high = spans("flag_pause_high")

    return {
        "tremor_events": tremor_events,
        "speed_fast": speed_fast,
        "speed_slow": speed_slow,
        "pause_low":  pause_low,
        "pause_high": pause_high
    }

def print_grouped_report(grouped):
    print("\n=== [TREMOR] TremorScore (Z-게이팅) ===")
    if grouped["tremor_events"]:
        for e in grouped["tremor_events"]:
            print(f"- {e['start']}–{e['end']}s | Tremor med/max {e['tremor_med']}/{e['tremor_max']} "
                  f"(ref) jitter~{e['jitter_med_pct']}%, shimmer~{e['shimmer_med_pct']}%, HNR~{e['hnr_med_db']} dB | z_max={e['z_max']}")
    else:
        print("  감지된 떨림 없음")

    print("\n=== [SPEED] 말속도 ===")
    if grouped["speed_fast"]:
        for e in grouped["speed_fast"]:
            print(f"- 과속  {e['start']}–{e['end']}s | speaking~{e['speaking_med']} sps, articulation~{e['artic_med']} sps")
    if grouped["speed_slow"]:
        for e in grouped["speed_slow"]:
            print(f"- 저속  {e['start']}–{e['end']}s | speaking~{e['speaking_med']} sps, articulation~{e['artic_med']} sps")
    if not grouped["speed_fast"] and not grouped["speed_slow"]:
        print("  과속/저속 구간 없음")

    print("\n=== [PAUSE] 휴지 ===")
    if grouped["pause_high"]:
        for e in grouped["pause_high"]:
            print(f"- 쉼 과다  {e['start']}–{e['end']}s | pause_ratio~{e['pause_med']}")
    else:
        print("  쉼 과다 구간 없음")

# =====================
# Tone (Intonation+Energy+Rhythm)
# =====================
def band_score(x, lo, hi):
    if x is None or not np.isfinite(x): 
        return 0.0
    if lo <= x <= hi: 
        return 1.0
    span = max(hi - lo, 1e-6)
    if x < lo: s = 1.0 - (lo - x) / span
    else:      s = 1.0 - (x - hi) / span
    return float(np.clip(s, 0.0, 1.0))

def _safe_band(x, lo, hi):
    if x is None or not np.isfinite(x): return None
    if lo <= x <= hi: return 1.0
    span = max(hi - lo, 1e-6)
    s = 1.0 - (abs((x - hi) if x > hi else (lo - x)) / span)
    return float(np.clip(s, 0.0, 1.0))

def _intonation_subscore(isumm, cfg):
    w = cfg["intonation_sub_weights"]
    s_range = _safe_band(isumm.get("f0_range_st"), *cfg["f0_range_target"])
    s_var   = _safe_band(isumm.get("pitch_var_st"), *cfg["pitch_var_target"])
    s_slope = _safe_band(isumm.get("ending_slope_hz_per_s"), *cfg["ending_slope_ok"])
    slope_val = isumm.get("ending_slope_hz_per_s")
    if slope_val is not None and abs(float(slope_val)) <= 0.2:
        s_slope = (s_slope or 0.0) * 0.9
    parts = [x for x in [s_range, s_slope, s_var] if x is not None]
    sc = float(np.average(parts, weights=[w["range"], w["slope"], w["var"]][:len(parts)])) if parts else 0.0
    if (isumm.get("f0_range_st", 0) < cfg["monotone_guards"]["range_lo"]
        and isumm.get("pitch_var_st", 0) < cfg["monotone_guards"]["var_lo"]):
        sc = min(sc, cfg["monotone_guards"]["cap"])
    return float(np.clip(sc, 0.0, 1.0))

def compute_tone_fixed(inton: dict, energy: dict|None, rhythm: dict|None, TONE_CFG=TONE_CFG):
    W = TONE_CFG["weights"].copy()
    isumm = (inton or {}).get("summary", {})
    sc_intonation = _intonation_subscore(isumm, TONE_CFG)

    esumm = (energy or {}).get("summary", {})
    s_en_stress = _safe_band(esumm.get("stress_rate"), *TONE_CFG["stress_rate_target"])
    s_en_var    = _safe_band(esumm.get("energy_var_db"), *TONE_CFG["energy_var_db_target"])
    s_en_bal    = _safe_band(esumm.get("balance"), 0.0, TONE_CFG["energy_balance_tol"])
    en_parts = [x for x in [s_en_stress, s_en_var, s_en_bal] if x is not None]
    sc_energy = float(np.mean(en_parts)) if en_parts else None

    rsumm = (rhythm or {}).get("summary", {})
    s_r_npvi = _safe_band(rsumm.get("npvi"), *TONE_CFG["npvi_target"])
    s_r_cv   = _safe_band(rsumm.get("syll_cv"), *TONE_CFG["syll_cv_target"])
    s_r_reg  = _safe_band(rsumm.get("regularity"), *TONE_CFG["regularity_target"])
    rh_parts = [x for x in [s_r_npvi, s_r_cv, s_r_reg] if x is not None]
    sc_rhythm = float(np.mean(rh_parts)) if rh_parts else None

    tone_0_1 = 0.0
    if sc_intonation is not None: tone_0_1 += W["intonation"] * sc_intonation
    if sc_energy     is not None: tone_0_1 += W["energy"]     * sc_energy
    if sc_rhythm     is not None: tone_0_1 += W["rhythm"]     * sc_rhythm
    tone_score = int(round(100 * tone_0_1))

    coverage = 0.0
    if sc_intonation is not None: coverage += W["intonation"]
    if sc_energy     is not None: coverage += W["energy"]
    if sc_rhythm     is not None: coverage += W["rhythm"]
    eff = (tone_0_1 / coverage) if coverage > 0 else 0.0

    def label_from_eff(e):
        if e >= 0.80: return "자신감 있고 안정적"
        if e >= 0.65: return "대체로 자연스러움"
        if e >= 0.50: return "다소 단조/불균형"
        return "단조/불안정"

    label = label_from_eff(eff)
    return {
      "tone_score": tone_score,
      "label": label,
      "coverage": round(coverage,2),
      "drivers": {
          "f0_range_st": isumm.get("f0_range_st"),
          "ending_slope_hz_per_s": isumm.get("ending_slope_hz_per_s"),
          "pitch_var_st": isumm.get("pitch_var_st"),
          **((energy or {}).get("summary", {})),
          **((rhythm or {}).get("summary", {})),
      }
    }
