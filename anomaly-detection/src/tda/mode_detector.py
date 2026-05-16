"""TDA 모드 판별 — 시간지연 임베딩 → ripser H1 → Persistence Image → Attention 분류."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

try:
    import ripser as ripser_lib
    _RIPSER_AVAILABLE = True
except ImportError:
    _RIPSER_AVAILABLE = False

try:
    from gudhi.representations import PersistenceImage
    _GUDHI_AVAILABLE = True
except ImportError:
    _GUDHI_AVAILABLE = False

TDA_APPLIANCES: frozenset[str] = frozenset({
    "전기밥솥",
    "식기세척기/건조기",
    "세탁기",
    "에어컨",
    "전기장판/담요",
    "제습기",
    "일반 냉장고",
    "김치냉장고",
})

# 가전별 글로벌 정규화 상한 — build_tda_references.ipynb와 반드시 동일하게 유지
APPLIANCE_MAX_W: dict[str, float] = {
    "에어컨":            50.0,
    "김치냉장고":        200.0,
    "제습기":            500.0,
    "세탁기":            700.0,
    "일반 냉장고":       400.0,
    "식기세척기/건조기": 2000.0,
    "전기밥솥":          1500.0,
    "전기장판/담요":     200.0,
}

# 가전별 TDA 윈도우 크기 오버라이드 — build_tda_references.ipynb와 반드시 동일하게 유지
WINDOW_SIZE_OVERRIDE: dict[str, int] = {
    "식기세척기/건조기": 2048,  # 68s — 세척 사이클 전체 포착
}

_EMBED_DIM = 3
_EMBED_LAG = 10
_MIN_POINTS = 50
_IMG_SIZE = 20
_MAX_EDGE_LEN = 0.5
_PI_BANDWIDTH = 0.05
WINDOW_SIZE = 512  # 30Hz 기준 약 17초 — builder.py 고정 윈도우와 반드시 동일하게 유지

_pi_instance: "PersistenceImage | None" = None


def _get_pi() -> "PersistenceImage | None":
    global _pi_instance
    if _pi_instance is None and _GUDHI_AVAILABLE:
        _pi_instance = PersistenceImage(
            bandwidth=_PI_BANDWIDTH,
            resolution=[_IMG_SIZE, _IMG_SIZE],
            im_range=[0, 1, 0, 1],
        )
    return _pi_instance


def _time_delay_embed(signal: np.ndarray) -> np.ndarray:
    n = len(signal) - (_EMBED_DIM - 1) * _EMBED_LAG
    if n <= 0:
        return np.empty((0, _EMBED_DIM))
    return np.stack(
        [signal[i: i + n] for i in range(0, _EMBED_DIM * _EMBED_LAG, _EMBED_LAG)],
        axis=1,
    )


def compute_fingerprint(signal: np.ndarray, max_w: float) -> list[float] | None:
    """P(t) 시계열 → Persistence Image 벡터 (H1).

    max_w: 가전별 글로벌 정규화 상한 (APPLIANCE_MAX_W 참조).
    ripser 미설치 또는 신호 길이 부족 시 None 반환.
    build_tda_references.ipynb와 동일한 파라미터.
    """
    if not (_RIPSER_AVAILABLE and _GUDHI_AVAILABLE):
        return None
    if len(signal) < _MIN_POINTS:
        return None

    norm = np.clip(signal / max_w, 0.0, 1.0)
    if norm.max() < 1e-6:
        return None

    if len(norm) > WINDOW_SIZE:
        step = len(norm) // WINDOW_SIZE
        norm = norm[::step][:WINDOW_SIZE]

    cloud = _time_delay_embed(norm)
    if len(cloud) < _MIN_POINTS:
        return None

    result = ripser_lib.ripser(cloud, maxdim=1, thresh=_MAX_EDGE_LEN)
    dgm = result["dgms"][1]

    if len(dgm) == 0:
        return [0.0] * (_IMG_SIZE * _IMG_SIZE)

    dgm_finite = dgm[dgm[:, 1] != np.inf]
    if len(dgm_finite) == 0:
        return [0.0] * (_IMG_SIZE * _IMG_SIZE)

    pi = _get_pi()
    if pi is None:
        return None

    img = pi.fit_transform([dgm_finite])
    return img[0].flatten().tolist()


def load_references(path: str | Path) -> dict:
    """reference_images.json 로드. 파일 없으면 빈 dict."""
    p = Path(path)
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def classify_mode(
    appliance: str,
    fingerprint: list[float],
    references: dict,
) -> str | None:
    """Persistence Image → 레퍼런스와 L2 거리 비교 → 최근접 모드명 (baseline).

    references가 없거나 fingerprint가 None이면 None 반환 → caller가 W 범위 룩업으로 폴백.
    영벡터 레퍼런스(데이터 없는 상태)는 비교 대상에서 제외.
    """
    app_refs = references.get(appliance)
    if not app_refs or fingerprint is None:
        return None

    fp = np.array(fingerprint, dtype=np.float32)
    best_state: str | None = None
    best_dist = float("inf")

    for state_name, ref_vec in app_refs.items():
        ref = np.array(ref_vec, dtype=np.float32)
        if not np.any(ref):
            continue
        dist = float(np.linalg.norm(fp - ref))
        if dist < best_dist:
            best_dist = dist
            best_state = state_name

    return best_state


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def classify_mode_attention(
    appliance: str,
    fingerprint: list[float],
    references: dict,
) -> tuple[str | None, float | None]:
    """Scaled Dot-Product Attention으로 레퍼런스 중 최근접 모드 반환.

    L2 대신 코사인 내적 기반 유사도를 softmax로 정규화해 분류.
    entropy가 낮을수록 분류 확신도 높음 (uniform → max entropy).

    Returns:
        (mode_name, entropy) — 레퍼런스 없거나 fingerprint None이면 (None, None).
    """
    app_refs = references.get(appliance)
    if not app_refs or fingerprint is None:
        return None, None

    fp = np.array(fingerprint, dtype=np.float32)
    fp_norm = fp / (np.linalg.norm(fp) + 1e-8)

    state_names: list[str] = []
    ref_vecs: list[np.ndarray] = []
    for state_name, ref_vec in app_refs.items():
        ref = np.array(ref_vec, dtype=np.float32)
        if not np.any(ref):
            continue
        ref_vecs.append(ref / (np.linalg.norm(ref) + 1e-8))
        state_names.append(state_name)

    if not state_names:
        return None, None

    K = np.stack(ref_vecs, axis=0)                         # [n_states, d]
    scores = (fp_norm @ K.T) / np.sqrt(K.shape[1])         # [n_states]
    weights = _softmax(scores)

    best_idx = int(np.argmax(weights))
    entropy = float(-np.sum(weights * np.log(weights + 1e-8)))

    return state_names[best_idx], entropy
