"""
TDA (Topological Data Analysis) 특징 추출.

compute_tda_features(signal) → np.ndarray shape (TDA_DIM,)

H0: 1D sublevel set filtration — 연결 성분 생애 (로컬 최솟값 기반 elder rule)
H1: 2D phase-space Rips complex — (signal[t], signal[t+1]) 루프 구조

GUDHI 없으면 H1 부분은 0으로 채운다.
"""

import numpy as np

TDA_DIM = 22  # 고정 출력 차원: H0(8) + H1(8) + signal_stats(4) + magnitude(2)


def compute_tda_features(signal: np.ndarray, n_subsample: int = 64) -> np.ndarray:
    """
    1D 신호 → TDA 특징 벡터 (TDA_DIM,).

    signal    : 1D float array (window_size,) — active_power 윈도우
    n_subsample: Rips complex 구성용 서브샘플 수 (속도 조절, 기본 64)
    """
    signal = np.asarray(signal, dtype=np.float32)

    # 서브샘플링 (등간격)
    if len(signal) > n_subsample:
        idx = np.linspace(0, len(signal) - 1, n_subsample, dtype=int)
        sig_sub = signal[idx]
    else:
        sig_sub = signal.copy()

    # 0~1 정규화 (TDA는 스케일에 민감)
    sig_range = float(sig_sub.max() - sig_sub.min())
    sig_norm = (sig_sub - sig_sub.min()) / sig_range if sig_range > 0 else sig_sub * 0.0

    h0 = _sublevel_h0_lifetimes(sig_norm)
    h1 = _rips_h1_lifetimes(sig_norm)

    h0_feat = _persistence_stats(h0, top_k=5)   # 8 features
    h1_feat = _persistence_stats(h1, top_k=5)   # 8 features

    # zero-crossing rate: 신호가 평균선을 넘는 횟수 (가전 동작 패턴 구분)
    zcr = float(np.sum(np.diff(np.sign(signal - signal.mean())) != 0))
    # log-scale magnitude: 절대 전력 수준 보존 (0~1 정규화로 소실되는 정보 복원)
    log_mean = float(np.log10(max(float(signal.mean()) + 1.0, 1e-6)))
    log_max  = float(np.log10(max(float(signal.max())  + 1.0, 1e-6)))
    sig_feat = np.array([
        signal.mean(),
        signal.std(),
        float(signal.max() - signal.min()),
        zcr,
        log_mean,
        log_max,
    ], dtype=np.float32)  # 6 features

    feat = np.concatenate([h0_feat, h1_feat, sig_feat])
    return feat[:TDA_DIM].astype(np.float32)


def _persistence_stats(lifetimes: np.ndarray, top_k: int = 5) -> np.ndarray:
    """persistence lifetime 배열 → top-k + [mean, std, count] = top_k+3 features."""
    top = np.zeros(top_k, dtype=np.float32)
    if len(lifetimes) > 0:
        sorted_lt = np.sort(lifetimes)[::-1]
        n = min(top_k, len(sorted_lt))
        top[:n] = sorted_lt[:n]
        stats = np.array([lifetimes.mean(), lifetimes.std(), float(len(lifetimes))], dtype=np.float32)
    else:
        stats = np.zeros(3, dtype=np.float32)
    return np.concatenate([top, stats])


def _sublevel_h0_lifetimes(signal: np.ndarray) -> np.ndarray:
    """
    1D sublevel set filtration → H0 persistence lifetimes.

    Elder rule: 두 component가 합쳐질 때 나중에 태어난 쪽(birth 값이 큰 쪽)이 죽는다.
    death value = 현재 처리 중인 signal 값 (두 component가 만나는 지점).
    lifetime = death - birth.
    """
    n = len(signal)
    parent = np.arange(n)
    birth = signal.copy()
    deaths: list[float] = []

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    active = np.zeros(n, dtype=bool)
    for i in np.argsort(signal):
        active[i] = True
        neighbors = [j for j in (i - 1, i + 1) if 0 <= j < n and active[j]]

        if len(neighbors) == 0:
            pass  # 새 component 탄생, birth[i] 이미 설정됨

        elif len(neighbors) == 1:
            ri = find(neighbors[0])
            if birth[ri] <= birth[i]:  # i의 component가 더 늦게 태어남 → i 죽음
                deaths.append(float(signal[i] - birth[i]))
                parent[i] = ri
            else:
                deaths.append(float(signal[i] - birth[ri]))
                parent[ri] = i
                birth[i] = birth[ri]

        else:  # 두 이웃 모두 active → 두 component 합병
            r0, r1 = find(neighbors[0]), find(neighbors[1])
            if r0 == r1:
                pass
            elif birth[r0] <= birth[r1]:  # r1이 더 늦게 태어남 → r1 죽음
                deaths.append(float(signal[i] - birth[r1]))
                parent[r1] = r0
            else:
                deaths.append(float(signal[i] - birth[r0]))
                parent[r0] = r1

    lifetimes = np.array(deaths, dtype=np.float32)
    return lifetimes[lifetimes > 0]  # 0 lifetime 제거


def _rips_h1_lifetimes(signal: np.ndarray) -> np.ndarray:
    """
    2D phase-space (signal[t], signal[t+1]) Rips complex → H1 persistence lifetimes.

    GUDHI 없으면 빈 배열 반환.
    """
    if len(signal) < 4:
        return np.zeros(0, dtype=np.float32)

    try:
        import gudhi  # type: ignore
    except ImportError:
        return np.zeros(0, dtype=np.float32)

    points = np.stack([signal[:-1], signal[1:]], axis=1).astype(np.float64)

    # 인접점 거리의 90th percentile × 2 를 최대 엣지 길이로 사용
    adj_dists = np.linalg.norm(np.diff(points, axis=0), axis=1)
    max_edge = float(np.percentile(adj_dists, 90)) * 2.0 if len(adj_dists) > 0 else 1.0

    rc = gudhi.RipsComplex(points=points, max_edge_length=max_edge)
    st = rc.create_simplex_tree(max_dimension=2)
    st.compute_persistence()

    h1 = [
        float(d - b)
        for dim, (b, d) in st.persistence()
        if dim == 1 and d != float("inf")
    ]
    return np.array(h1, dtype=np.float32) if h1 else np.zeros(0, dtype=np.float32)
